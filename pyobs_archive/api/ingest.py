"""Coordinate ingest publication on local macOS/Linux filesystems.

The database and filesystem cannot commit atomically. See development.rst for
crash recovery and the shared-filesystem locking requirements.
"""
import fcntl
import hashlib
import json
import logging
import os
import shutil
import tempfile
from contextlib import contextmanager

from django.db import InterfaceError, OperationalError, transaction

log = logging.getLogger(__name__)


@contextmanager
def _basename_lock(root, basename):
    directory = os.path.join(root, '.ingest-locks')
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, hashlib.sha256(basename.encode()).hexdigest())
    # Never unlink: concurrent waiters must keep referring to the same inode.
    with open(path, 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield path + '.recovery'
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _remove(path):
    if path is not None:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            log.exception('Ingest cleanup required for %s', path)


def _stage(directory, data):
    path = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.ingest-', delete=False) as stream:
            path = stream.name
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return path
    except BaseException:
        _remove(path)
        raise


def _backup(filename):
    # Copy instead of moving so readers can continue using the original file.
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(filename),
                                     prefix='.ingest-backup-', delete=False) as stream:
        backup = stream.name
    try:
        shutil.copy2(filename, backup)
        return backup
    except BaseException:
        _remove(backup)
        raise


def publish_frame(root, basename, filename, data, update_frame):
    """Publish bytes and metadata, compensating ordinary failures under a lock.

    ``update_frame`` runs inside an outermost transaction and returns the previous
    filename (if any). It must perform all database/relationship updates here.
    """
    if not transaction.get_autocommit():
        raise RuntimeError('Ingest requires autocommit outside any transaction.')
    directory = os.path.dirname(filename)
    os.makedirs(directory, exist_ok=True)
    staged = _stage(directory, data)
    try:
        with _basename_lock(root, basename) as recovery:
            if os.path.exists(recovery):
                raise RuntimeError('Ingest requires manual reconciliation: %s' % recovery)
            backup = None
            published = False
            committing = False
            committed = False

            def mark_committed():
                nonlocal committed
                committed = True

            try:
                with transaction.atomic(durable=True):
                    # Register first so later on_commit hooks cannot make a
                    # successful commit look like a rollback-safe failure.
                    transaction.on_commit(mark_committed)
                    old_filename = update_frame()
                    if os.path.exists(filename):
                        backup = _backup(filename)
                    os.replace(staged, filename)
                    published = True
                    committing = True
            except BaseException as exc:
                if committed:
                    log.exception('Ingest committed for %s, but a post-commit hook failed', filename)
                    if not isinstance(exc, Exception):
                        raise
                else:
                    # A disconnected database can make COMMIT's outcome unknowable.
                    # Retain the new file and original backup for manual reconciliation.
                    uncertain = committing and isinstance(exc, (OperationalError, InterfaceError))
                    if published and not uncertain:
                        try:
                            if backup is None:
                                os.unlink(filename)
                            else:
                                os.replace(backup, filename)
                                backup = None
                        except OSError:
                            uncertain = True
                            log.exception('Could not restore %s; backup is %s', filename, backup)
                    if uncertain:
                        log.critical('Ingest recovery required for %s; backup=%s; marker=%s',
                                     filename, backup, recovery)
                        # Block another ingest of this basename from destroying evidence.
                        try:
                            with open(recovery, 'x') as stream:
                                json.dump({'filename': filename, 'backup': backup,
                                           'error': repr(exc)}, stream)
                        except OSError:
                            log.exception('Could not write recovery marker %s', recovery)
                    else:
                        _remove(backup)
                    raise
            # Commit succeeded: housekeeping cannot turn this into a failed ingest.
            _remove(backup)
            if old_filename is not None and os.path.realpath(old_filename) != filename:
                _remove(old_filename)
    finally:
        _remove(staged)
