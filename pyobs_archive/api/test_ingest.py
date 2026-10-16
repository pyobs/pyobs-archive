"""Regression coverage for issue #74, including real commits and file failures."""
import io
import multiprocessing
import os
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from pathlib import Path
from unittest import mock

import numpy as np
from astropy.io import fits
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, OperationalError, connection, connections, transaction
from django.test import TransactionTestCase
from PIL import Image

from . import ingest
from .models import Frame
from .tests import _header, _make_frame


REAL_POPEN = subprocess.Popen
FPACK = shutil.which('fpack')


def image_bytes(value=1, **headers):
    science = fits.ImageHDU(np.full((10, 10), value, dtype=np.int16), name='SCI')
    for key, val in _header(**headers).items():
        if key not in ('NAXIS1', 'NAXIS2'):
            science.header[key] = val
    with io.BytesIO() as stream:
        fits.HDUList([fits.PrimaryHDU(), science]).writeto(stream)
        return stream.getvalue()


def _concurrent_publish(root, entered, release, attempted, result, first, fail=False):
    connections.close_all()
    try:
        attempted.set()

        def update():
            entered.set()
            if first and not release.wait(10):
                raise RuntimeError('Timed out waiting for competing publisher')
            frame = Frame.objects.filter(basename='shared').first()
            if frame is None:
                frame = _make_frame('shared')
            frame.OBJECT = 'first' if first else 'second'
            frame.save()
            return None

        failure = (mock.patch.object(connection, 'commit', side_effect=IntegrityError('first failed'))
                   if fail else nullcontext())
        with failure:
            ingest.publish_frame(root, 'shared', os.path.join(root, 'shared.fits.fz'),
                                 b'first' if first else b'second', update)
        result.put((first, None))
    except BaseException as exc:
        result.put((first, repr(exc)))
    finally:
        connections.close_all()


class FrameIngestTests(TransactionTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.settings(ARCHIVE_ROOT=str(self.root), PATH_FORMATTER='{SITEID}',
                                    FILENAME_FORMATTER=None, PORTAL_URL='', PORTAL_TOKEN='')
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.output = image_bytes()
        self.process = mock.Mock(returncode=0)
        self.process.communicate.return_value = (self.output, b'')
        self.which = mock.patch('pyobs_archive.api.models.shutil.which',
                                return_value='/opt/homebrew/bin/fpack').start()
        self.popen = mock.patch('pyobs_archive.api.models.subprocess.Popen',
                                return_value=self.process).start()
        self.addCleanup(mock.patch.stopall)
        self.final = self.root / 'iag' / 'test_frame.fits.fz'

    def store(self, **headers):
        return Frame.ingest(io.BytesIO(image_bytes(**headers)))

    def assert_clean(self):
        self.assertEqual([p for p in self.root.rglob('.ingest-*') if p.is_file()], [])

    def existing(self):
        frame = _make_frame('test_frame', path='iag', OBJECT='original')
        related = _make_frame('bias')
        frame.related.add(related)
        self.final.parent.mkdir()
        self.final.write_bytes(b'original image')
        return frame, related

    def assert_original(self, frame, related):
        frame.refresh_from_db()
        self.assertEqual(frame.OBJECT, 'original')
        self.assertEqual(list(frame.related.all()), [related])
        self.assertEqual(self.final.read_bytes(), b'original image')
        self.assert_clean()

    def test_success_uses_path_and_publishes_valid_image(self):
        related = _make_frame('bias')
        self.assertEqual(self.store(L1BIAS='bias'), 'test_frame')
        frame = Frame.objects.get(basename='test_frame')
        self.assertEqual(list(frame.related.all()), [related])
        self.assertEqual(frame.width, 10)
        self.assertEqual(self.final.read_bytes(), self.output)
        self.assertEqual(self.popen.call_args.args[0], ['/opt/homebrew/bin/fpack', '-S', '-'])
        serialized = self.process.communicate.call_args.args[0]
        with fits.open(io.BytesIO(serialized)) as hdus:
            self.assertEqual(hdus['SCI'].header['FNAME'], 'test_frame')
        self.assert_clean()

    def test_real_fpack_round_trip_from_nonstandard_path(self):
        if FPACK is None:
            self.skipTest('CFITSIO fpack is not installed')
        binary = self.root / 'bin' / 'fpack'
        binary.parent.mkdir()
        binary.symlink_to(FPACK)
        self.which.return_value = str(binary)
        self.popen.side_effect = REAL_POPEN
        self.store()
        with fits.open(self.final) as hdus:
            np.testing.assert_array_equal(hdus['SCI'].data, np.ones((10, 10)))
        frame = Frame.objects.get(basename='test_frame')
        self.store(OBJECT='replacement')
        self.assertEqual(Frame.objects.get(basename='test_frame').pk, frame.pk)
        self.assert_clean()

    def test_missing_compressor(self):
        self.which.return_value = None
        with self.assertRaisesRegex(ValueError, 'fpack.*PATH'):
            self.store()
        self.assertEqual(Frame.objects.count(), 0)
        self.assertFalse(self.final.exists())
        self.popen.assert_not_called()

    def test_launch_failure_keeps_original(self):
        frame, related = self.existing()
        self.popen.side_effect = FileNotFoundError('gone')
        with self.assertRaisesRegex(ValueError, 'Could not launch fpack'):
            self.store()
        self.assert_original(frame, related)

    def test_compressor_failure_keeps_original(self):
        frame, related = self.existing()
        self.process.returncode = 1
        self.process.communicate.return_value = (b'partial', b'bad input')
        with self.assertRaisesRegex(ValueError, 'status 1: bad input'):
            self.store()
        self.assert_original(frame, related)

    def test_invalid_compressor_output_never_published(self):
        with io.BytesIO() as stream:
            fits.PrimaryHDU().writeto(stream)
            no_science = stream.getvalue()
        for data in (b'', b'invalid FITS', no_science):
            with self.subTest(data=data[:20]):
                self.process.communicate.return_value = (data, b'')
                with self.assertRaisesRegex(ValueError, 'fpack returned'):
                    self.store()
                self.assertEqual(Frame.objects.count(), 0)
                self.assertFalse(self.final.exists())
        self.assert_clean()

    def test_serialization_failure_closes_input_and_keeps_database_clean(self):
        hdus = fits.open(io.BytesIO(image_bytes()))
        with mock.patch('pyobs_archive.api.models.fits.open', return_value=hdus), \
                mock.patch.object(hdus, 'writeto', side_effect=OSError('serialize')):
            with self.assertRaisesRegex(OSError, 'serialize'):
                self.store()
        self.assertEqual(Frame.objects.count(), 0)
        self.popen.assert_not_called()

    def test_stage_flush_failure_keeps_original(self):
        frame, related = self.existing()
        with mock.patch.object(ingest.os, 'fsync', side_effect=OSError('flush')):
            with self.assertRaisesRegex(OSError, 'flush'):
                self.store()
        self.assert_original(frame, related)

    def test_stage_write_failure_keeps_original(self):
        frame, related = self.existing()
        original = ingest.tempfile.NamedTemporaryFile

        def broken_stream(**kwargs):
            stream = original(**kwargs)
            stream.write = mock.Mock(side_effect=OSError('write'))
            return stream

        with mock.patch.object(ingest.tempfile, 'NamedTemporaryFile', side_effect=broken_stream):
            with self.assertRaisesRegex(OSError, 'write'):
                self.store()
        self.assert_original(frame, related)

    def test_save_failure_rolls_back_new_record(self):
        save = Frame.save

        def fail_after_save(frame, *args, **kwargs):
            save(frame, *args, **kwargs)
            raise IntegrityError('save')

        with mock.patch.object(Frame, 'save', fail_after_save):
            with self.assertRaisesRegex(IntegrityError, 'save'):
                self.store()
        self.assertEqual(Frame.objects.count(), 0)
        self.assertFalse(self.final.exists())
        self.assert_clean()

    def test_related_failure_rolls_back_replacement(self):
        frame, related = self.existing()
        link = Frame.link_related

        def fail_after_links(frame, header):
            link(frame, header)
            raise IntegrityError('links')

        with mock.patch.object(Frame, 'link_related', fail_after_links):
            with self.assertRaisesRegex(IntegrityError, 'links'):
                self.store()
        self.assert_original(frame, related)

    def test_backup_failure_keeps_original(self):
        frame, related = self.existing()
        with mock.patch.object(ingest.shutil, 'copy2', side_effect=OSError('backup')):
            with self.assertRaisesRegex(OSError, 'backup'):
                self.store()
        self.assert_original(frame, related)

    def test_replace_failure_keeps_original(self):
        frame, related = self.existing()
        with mock.patch.object(ingest.os, 'replace', side_effect=OSError('replace')):
            with self.assertRaisesRegex(OSError, 'replace'):
                self.store()
        self.assert_original(frame, related)

    def test_commit_failure_restores_original_and_links(self):
        frame, related = self.existing()
        with mock.patch.object(connection, 'commit', side_effect=IntegrityError('commit')):
            with self.assertRaisesRegex(IntegrityError, 'commit'):
                self.store()
        self.assert_original(frame, related)

    def test_commit_failure_removes_new_file_and_record(self):
        with mock.patch.object(connection, 'commit', side_effect=IntegrityError('commit')):
            with self.assertRaisesRegex(IntegrityError, 'commit'):
                self.store()
        self.assertEqual(Frame.objects.count(), 0)
        self.assertFalse(self.final.exists())
        self.assert_clean()

    def test_commit_failure_restores_orphan_destination(self):
        self.final.parent.mkdir()
        self.final.write_bytes(b'orphan')
        with mock.patch.object(connection, 'commit', side_effect=IntegrityError('commit')):
            with self.assertRaisesRegex(IntegrityError, 'commit'):
                self.store()
        self.assertEqual(self.final.read_bytes(), b'orphan')
        self.assertEqual(Frame.objects.count(), 0)
        self.assert_clean()

    def test_successful_replacement_preserves_identity_and_updates_links(self):
        frame, _ = self.existing()
        other = _make_frame('other')
        self.store(OBJECT='new', L1BIAS='other')
        frame.refresh_from_db()
        self.assertEqual(frame.pk, Frame.objects.get(basename='test_frame').pk)
        self.assertEqual(frame.OBJECT, 'new')
        self.assertEqual(list(frame.related.all()), [other])
        self.assertEqual(self.final.read_bytes(), self.output)
        self.assert_clean()

    def test_changed_directory_only_removes_old_file_after_commit(self):
        frame, _ = self.existing()
        self.store(SITEID='new')
        frame.refresh_from_db()
        self.assertEqual(frame.path, 'new')
        self.assertFalse(self.final.exists())
        self.assertEqual(Path(frame.filename).read_bytes(), self.output)
        self.assert_clean()

    def test_changed_directory_commit_failure_keeps_both_original_destinations(self):
        frame, related = self.existing()
        other = self.root / 'new' / self.final.name
        other.parent.mkdir()
        other.write_bytes(b'orphan')
        with mock.patch.object(connection, 'commit', side_effect=IntegrityError('commit')):
            with self.assertRaises(IntegrityError):
                self.store(SITEID='new')
        self.assert_original(frame, related)
        self.assertEqual(other.read_bytes(), b'orphan')
        self.assertEqual(frame.path, 'iag')

    def test_post_commit_cleanup_failure_still_returns_success(self):
        frame, _ = self.existing()
        unlink = os.unlink

        def fail_backup_cleanup(path, *args, **kwargs):
            if '.ingest-backup-' in str(path):
                raise OSError('cleanup')
            return unlink(path, *args, **kwargs)

        with mock.patch.object(ingest.os, 'unlink', side_effect=fail_backup_cleanup), \
                self.assertLogs(ingest.log, level='ERROR'):
            self.assertEqual(self.store(), 'test_frame')
        frame.refresh_from_db()
        self.assertEqual(frame.OBJECT, 'M31')
        self.assertEqual(self.final.read_bytes(), self.output)
        self.assertEqual(len(list(self.root.rglob('.ingest-backup-*'))), 1)

    def test_compensation_failure_preserves_backup_and_blocks_next_ingest(self):
        self.existing()
        replace = os.replace

        def fail_restore(source, destination):
            if '.ingest-backup-' in str(source):
                raise OSError('restore')
            return replace(source, destination)

        with mock.patch.object(connection, 'commit', side_effect=IntegrityError('commit')), \
                mock.patch.object(ingest.os, 'replace', side_effect=fail_restore), \
                self.assertLogs(ingest.log, level='ERROR'):
            with self.assertRaisesRegex(IntegrityError, 'commit'):
                self.store()
        backup, = self.root.rglob('.ingest-backup-*')
        self.assertEqual(backup.read_bytes(), b'original image')
        with self.assertRaisesRegex(RuntimeError, 'manual reconciliation'):
            self.store()

    def test_uncertain_commit_preserves_both_images_and_blocks_next_ingest(self):
        self.existing()
        with mock.patch.object(connection, 'commit', side_effect=OperationalError('disconnect')), \
                self.assertLogs(ingest.log, level='CRITICAL'):
            with self.assertRaisesRegex(OperationalError, 'disconnect'):
                self.store()
        self.assertEqual(self.final.read_bytes(), self.output)
        backup, = self.root.rglob('.ingest-backup-*')
        self.assertEqual(backup.read_bytes(), b'original image')
        with self.assertRaisesRegex(RuntimeError, 'manual reconciliation'):
            self.store()

    def test_nested_transaction_rejected_before_publication(self):
        with transaction.atomic():
            with self.assertRaisesRegex(RuntimeError, 'outside any transaction'):
                self.store()
        self.assertEqual(Frame.objects.count(), 0)
        self.assertFalse(self.final.exists())
        self.assert_clean()

    def test_disabled_autocommit_rejected_before_publication(self):
        transaction.set_autocommit(False)
        try:
            with self.assertRaisesRegex(RuntimeError, 'autocommit'):
                self.store()
        finally:
            transaction.rollback()
            transaction.set_autocommit(True)
        self.assertEqual(Frame.objects.count(), 0)
        self.assertFalse(self.final.exists())
        self.assert_clean()

    def test_post_commit_hook_failure_keeps_committed_image(self):
        frame, _ = self.existing()
        link = Frame.link_related

        def link_and_register_hook(frame, header):
            link(frame, header)

            def fail():
                raise RuntimeError('post-commit hook')

            transaction.on_commit(fail)

        with mock.patch.object(Frame, 'link_related', link_and_register_hook), \
                self.assertLogs(ingest.log, level='ERROR'):
            self.assertEqual(self.store(), 'test_frame')
        frame.refresh_from_db()
        self.assertEqual(frame.OBJECT, 'M31')
        self.assertEqual(self.final.read_bytes(), self.output)
        self.assert_clean()

    def test_upload_response_counts_success_and_reports_failures(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_superuser('admin', password='secret'))
        self.process.communicate.side_effect = [(b'partial', b'bad'), (self.output, b'')]
        self.process.returncode = 0
        response = self.client.post('/frames/create/', {
            'bad': SimpleUploadedFile('bad.fits', image_bytes(FNAME='bad')),
            'good': SimpleUploadedFile('good.fits', image_bytes()),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['created'], 1)
        self.assertEqual(response.json()['filenames'], ['test_frame'])
        self.assertEqual(len(response.json()['errors']), 1)
        self.assertFalse(Frame.objects.filter(basename='bad').exists())

    def test_same_basename_publications_serialize_across_processes(self):
        if connection.vendor != 'sqlite' or 'memory' in str(connection.settings_dict['NAME']):
            self.skipTest('Requires a file-backed SQLite test database')
        for existing, fail in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(existing=existing, first_commit_fails=fail):
                Frame.objects.all().delete()
                target = self.root / 'shared.fits.fz'
                if existing:
                    _make_frame('shared')
                    target.write_bytes(b'original')
                ctx = multiprocessing.get_context('fork')
                entered1, entered2, release = ctx.Event(), ctx.Event(), ctx.Event()
                attempted1, attempted2, result = ctx.Event(), ctx.Event(), ctx.Queue()
                first = ctx.Process(target=_concurrent_publish,
                                    args=(str(self.root), entered1, release, attempted1, result, True, fail))
                second = ctx.Process(target=_concurrent_publish,
                                     args=(str(self.root), entered2, release, attempted2, result, False))
                connections.close_all()
                try:
                    first.start()
                    self.assertTrue(entered1.wait(10))
                    second.start()
                    self.assertTrue(attempted2.wait(10))
                    self.assertFalse(entered2.wait(0.2), 'Competing writer entered while lock held')
                    release.set()
                    first.join(10)
                    second.join(10)
                    self.assertEqual(first.exitcode, 0)
                    self.assertEqual(second.exitcode, 0)
                    outcomes = dict([result.get(timeout=2), result.get(timeout=2)])
                    self.assertIsNone(outcomes[False])
                    if fail:
                        self.assertIn('first failed', outcomes[True])
                    else:
                        self.assertIsNone(outcomes[True])
                    self.assertEqual(Frame.objects.get(basename='shared').OBJECT, 'second')
                    self.assertEqual(target.read_bytes(), b'second')
                finally:
                    release.set()
                    for process in (first, second):
                        if process.pid and process.is_alive():
                            process.terminate()
                            process.join(5)
                    result.close()


class PreviewOrientationTests(TransactionTestCase):
    def test_first_fits_row_is_at_bottom(self):
        from django.contrib.auth.models import User
        from .views import preview_view
        from django.test import RequestFactory

        data = np.zeros((10, 10), dtype=np.int16)
        data[:5] = 100
        with tempfile.TemporaryDirectory() as root, self.settings(ARCHIVE_ROOT=root,
                                                               PROJECT_ACCESS_CONTROL=False):
            frame = _make_frame('orientation', path='')
            fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data, name='SCI')]).writeto(frame.filename)
            request = RequestFactory().get('/frames/%d/preview/' % frame.pk)
            request.user = User.objects.create_user('viewer')
            response = preview_view(request, frame.pk)
            self.assertEqual(response.status_code, 200)
            png = np.asarray(Image.open(io.BytesIO(response.content)).convert('L'))
            self.assertLess(png[25:75, 25:175].mean(), png[125:175, 25:175].mean())
