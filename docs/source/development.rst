Development
###########

Running locally, without Docker::

    git clone https://github.com/pyobs/pyobs-archive.git
    cd pyobs-archive
    uv run manage.py migrate
    uv run manage.py createsuperuser
    uv run manage.py runserver

With no configuration at all, this runs against a local SQLite database. Open
``http://localhost:8000/`` and log in with the superuser you created.

Setting ``ADMIN_USERNAME``/``ADMIN_PASSWORD_HASH`` (see :doc:`configuration`) syncs a matching
superuser automatically after every ``migrate``, skipping the interactive ``createsuperuser`` step
— handy for scripted/Docker deployments.

Create another user for ingesting new images (called ``pyobs`` here) and the token it needs to
send new images (see :doc:`api`)::

    uv run manage.py createsuperuser
    uv run manage.py drf_create_token pyobs

Tests::

    uv run manage.py test

Native ingestion requires CFITSIO's ``fpack`` executable (for example,
``brew install cfitsio`` on macOS or ``apt install libcfitsio-bin`` on Debian).
The server process must inherit a ``PATH`` containing its bin directory; setting
PATH only in an interactive shell does not configure a separately launched
service. The Docker image already installs this dependency.

Ingest publication and recovery
===============================

Ingest compresses and validates the image before changing its database record.
It stages files beside the destination, then replaces the destination atomically
inside an outermost database transaction. Ordinary failures roll back metadata
and related links and restore any original destination. Updating a basename
preserves its database identity; an old file in a different directory is removed
only after commit. Post-commit cleanup errors are logged and leave the committed
image usable.

Writers serialize by basename using persistent advisory lock files under
``ARCHIVE_ROOT/.ingest-locks``. All ingest processes must share that root on a
filesystem supporting ``flock`` (macOS/Linux). Do not delete lock files while
writers are running. This does not coordinate concurrent manual deletion or
provide distributed-storage locking. Call ingest outside any surrounding
transaction, including ``ATOMIC_REQUESTS``; its durable transaction must commit
before its file backup is discarded.

A filesystem rename and database commit are separate operations. Process death
or power loss between them may require manual recovery; metadata and file bytes
are not simultaneously visible to readers. A database disconnect during commit
has an uncertain outcome: ingest retains the destination and backup, logs their
paths, and writes a ``.recovery`` marker beside the basename's lock. Failed file
restoration also preserves recovery evidence and blocks further ingests of that
basename. Stop writers, reconcile the database row and files, restore the backup
if needed, and remove the marker only after reconciliation. Never run destructive
archive repair automatically. Leftover ``.ingest-*`` files after a crash or
logged cleanup failure should likewise be inspected with writers stopped.
