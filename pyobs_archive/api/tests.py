import tempfile
from unittest import mock

import requests
from astropy.io import fits
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, RequestFactory
from rest_framework.exceptions import ParseError

from pyobs_archive.api.backend import BackendUnavailable
from pyobs_archive.api.models import Frame, Project
from pyobs_archive.api.views import filter_frames, sort_frames


def _header(**overrides):
    values = {
        'DATE-OBS': '2024-01-15T10:00:00',
        'DAY-OBS': '2024-01-15',
        'NAXIS1': 100,
        'NAXIS2': 100,
        'XBINNING': 1,
        'YBINNING': 1,
        'FNAME': 'test_frame',
        'SITEID': 'iag',
        'TELID': 'iag50',
        'INSTRUME': 'cam1',
        'IMAGETYP': 'object',
        'OBJECT': 'M31',
        'EXPTIME': 30.0,
        'FILTER': 'clear',
        'REQNUM': '12345',
        'OBSNUM': '20240115-001',
    }
    values.update(overrides)
    header = fits.Header()
    for key, value in values.items():
        if value is not None:
            header[key] = value
    return header


class FrameAddFitsHeaderTests(TestCase):
    def test_sets_core_fields_from_header(self):
        frame = Frame()
        frame.add_fits_header(_header())

        self.assertEqual(frame.basename, 'test_frame')
        self.assertEqual(frame.SITEID, 'iag')
        self.assertEqual(str(frame.night), '2024-01-15')
        self.assertEqual(frame.width, 100)
        self.assertEqual(frame.height, 100)

    def test_parses_reqnum_and_obsnum(self):
        frame = Frame()
        frame.add_fits_header(_header(REQNUM='42', OBSNUM='20240115-003'))

        self.assertEqual(frame.REQNUM, '42')
        self.assertEqual(frame.OBSNUM, '20240115-003')

    def test_obsnum_defaults_to_none_when_absent(self):
        header = _header()
        del header['OBSNUM']

        frame = Frame()
        frame.add_fits_header(header)

        self.assertIsNone(frame.OBSNUM)

    def test_missing_date_obs_raises(self):
        header = _header()
        del header['DATE-OBS']

        with self.assertRaises(ValueError):
            Frame().add_fits_header(header)


class FilterFramesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        self.frame_a = Frame.objects.create(
            basename='frame_a', path='p', SITEID='site1', TELID='tel1', INSTRUME='inst1',
            IMAGETYP='object', DATE_OBS='2024-01-15T10:00:00Z', night='2024-01-15',
            OBJECT='M31', EXPTIME=30.0, FILTER='clear', RLEVEL=0,
            XBINNING=1, YBINNING=1, width=100, height=100,
            REQNUM='100', OBSNUM='20240115-001',
        )
        self.frame_b = Frame.objects.create(
            basename='frame_b', path='p', SITEID='site2', TELID='tel2', INSTRUME='inst2',
            IMAGETYP='bias', DATE_OBS='2024-01-16T10:00:00Z', night='2024-01-16',
            OBJECT='M42', EXPTIME=0.0, FILTER=None, RLEVEL=1,
            XBINNING=2, YBINNING=2, width=100, height=100,
            REQNUM='200', OBSNUM='20240116-001',
        )

    def _filtered(self, **params):
        request = self.factory.get('/frames/', params)
        return filter_frames(Frame.objects.all(), request)

    def test_no_filters_returns_all(self):
        self.assertEqual(self._filtered().count(), 2)

    def test_filter_by_obsnum(self):
        result = self._filtered(OBSNUM='20240115-001')
        self.assertEqual(list(result), [self.frame_a])

    def test_filter_by_reqnum(self):
        result = self._filtered(REQNUM='200')
        self.assertEqual(list(result), [self.frame_b])

    def test_filter_by_object_icontains(self):
        result = self._filtered(OBJECT='m31')
        self.assertEqual(list(result), [self.frame_a])

    def test_filter_by_night(self):
        result = self._filtered(night='2024-01-16')
        self.assertEqual(list(result), [self.frame_b])

    def test_filter_by_basename_icontains(self):
        result = self._filtered(basename='FRAME_A')
        self.assertEqual(list(result), [self.frame_a])

    def test_filter_by_exptime_gte(self):
        result = self._filtered(EXPTIME='10')
        self.assertEqual(list(result), [self.frame_a])

    def test_filter_by_imagetype(self):
        result = self._filtered(IMAGETYPE='bias')
        self.assertEqual(list(result), [self.frame_b])

    def test_filter_by_rlevel(self):
        result = self._filtered(RLEVEL='1')
        self.assertEqual(list(result), [self.frame_b])

    def test_filter_by_filter_none(self):
        result = self._filtered(FILTER='None')
        self.assertEqual(list(result), [self.frame_b])

    def test_filter_by_binning(self):
        result = self._filtered(binning='2x2')
        self.assertEqual(list(result), [self.frame_b])


class SortFramesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.frame_a = Frame.objects.create(
            basename='frame_a', path='p', SITEID='site1', TELID='tel1', INSTRUME='inst1',
            IMAGETYP='object', DATE_OBS='2024-01-15T10:00:00Z', night='2024-01-15',
            OBJECT='M31', EXPTIME=30.0, FILTER='clear', RLEVEL=0,
            XBINNING=1, YBINNING=1, width=100, height=100,
        )
        self.frame_b = Frame.objects.create(
            basename='frame_b', path='p', SITEID='site2', TELID='tel2', INSTRUME='inst2',
            IMAGETYP='bias', DATE_OBS='2024-01-16T10:00:00Z', night='2024-01-16',
            OBJECT='M42', EXPTIME=0.0, FILTER=None, RLEVEL=1,
            XBINNING=2, YBINNING=2, width=100, height=100,
        )

    def _sorted(self, **params):
        request = self.factory.get('/frames/', params)
        return sort_frames(Frame.objects.all(), request)

    def test_default_sort_is_date_obs_ascending(self):
        self.assertEqual(list(self._sorted()), [self.frame_a, self.frame_b])

    def test_sort_desc(self):
        result = self._sorted(sort='DATE_OBS', order='desc')
        self.assertEqual(list(result), [self.frame_b, self.frame_a])

    def test_unknown_sort_field_raises_parse_error_not_500(self):
        with self.assertRaises(ParseError):
            self._sorted(sort='; DROP TABLE api_frame')

    def test_unknown_order_raises_parse_error(self):
        with self.assertRaises(ParseError):
            self._sorted(order='sideways')


class FrameIngestPathSafetyTests(TestCase):
    def setUp(self):
        self.archive_root = tempfile.mkdtemp()

    def _write_fits(self, **header_overrides):
        primary = fits.PrimaryHDU()
        sci = fits.ImageHDU(name='SCI')
        sci.header['DATE-OBS'] = '2024-01-15T10:00:00'
        sci.header['DAY-OBS'] = '2024-01-15'
        sci.header['SITEID'] = 'site1'
        sci.header['FNAME'] = 'testframe'
        for key, value in header_overrides.items():
            sci.header[key] = value
        hdul = fits.HDUList([primary, sci])
        tmp = tempfile.NamedTemporaryFile(suffix='.fits', delete=False)
        hdul.writeto(tmp.name, overwrite=True)
        return tmp.name

    def test_path_traversal_via_header_value_is_rejected(self):
        filename = self._write_fits(SITEID='../../../etc')
        with self.settings(ARCHIVE_ROOT=self.archive_root, PATH_FORMATTER='{SITEID}/{DAY-OBS}/',
                            FILENAME_FORMATTER=None):
            with self.assertRaises(ValueError):
                Frame.ingest(filename)

    def test_absolute_path_via_header_value_is_rejected(self):
        filename = self._write_fits(SITEID='/etc')
        with self.settings(ARCHIVE_ROOT=self.archive_root, PATH_FORMATTER='{SITEID}/{DAY-OBS}/',
                            FILENAME_FORMATTER=None):
            with self.assertRaises(ValueError):
                Frame.ingest(filename)

    def test_basename_with_separator_is_rejected(self):
        filename = self._write_fits(FNAME='../evil')
        with self.settings(ARCHIVE_ROOT=self.archive_root, PATH_FORMATTER='{SITEID}/{DAY-OBS}/',
                            FILENAME_FORMATTER='{FNAME}'):
            with self.assertRaises(ValueError):
                Frame.ingest(filename)


class FrameProjectIngestTests(TestCase):
    """PROJECT association: FITS header, REQNUM->project fallback via the robotic backend."""

    def test_project_read_from_header(self):
        frame = Frame()
        frame.add_fits_header(_header(PROJECT='XYZ001'))
        self.assertEqual(frame.PROJECT, 'XYZ001')

    def test_project_defaults_to_none_when_absent(self):
        frame = Frame()
        frame.add_fits_header(_header())
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.BackendClient')
    def test_reqnum_fallback_resolves_project(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.return_value = [{'id': 12345, 'project': 'XYZ001'}]

        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            frame.resolve_project_from_reqnum()

        self.assertEqual(frame.PROJECT, 'XYZ001')
        mock_client_cls.assert_called_once_with(
            'https://backend.example.org', 'tok', timeout=mock.ANY
        )

    def test_reqnum_fallback_is_noop_when_project_already_set(self):
        frame = Frame()
        frame.add_fits_header(_header(PROJECT='ABC001', REQNUM='999'))
        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            frame.resolve_project_from_reqnum()
        self.assertEqual(frame.PROJECT, 'ABC001')

    def test_reqnum_fallback_is_noop_without_reqnum(self):
        header = _header()
        del header['REQNUM']

        frame = Frame()
        frame.add_fits_header(header)
        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            frame.resolve_project_from_reqnum()
        self.assertIsNone(frame.PROJECT)

    def test_backend_not_configured_leaves_project_none(self):
        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(ROBOTIC_BACKEND_URL='', ROBOTIC_BACKEND_TOKEN=''):
            frame.resolve_project_from_reqnum()  # should not raise
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.BackendClient')
    def test_backend_unavailable_leaves_project_none(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.side_effect = BackendUnavailable('boom')

        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            frame.resolve_project_from_reqnum()  # should not raise
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.BackendClient')
    def test_reqnum_not_in_task_map_leaves_project_none(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.return_value = [{'id': 1, 'project': 'OTHER'}]

        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            frame.resolve_project_from_reqnum()
        self.assertIsNone(frame.PROJECT)


def _mock_response(json_data, status_code=200):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


class SyncProjectsCommandTests(TestCase):
    """`manage.py sync_projects`: upserts + reconciles the local Project mirror."""

    def setUp(self):
        self.alice = User.objects.create_user('alice')
        self.bob = User.objects.create_user('bob')

    @mock.patch('pyobs_archive.api.backend.requests.get')
    def test_creates_projects_and_reconciles_members_across_pages(self, mock_get):
        page1 = _mock_response({
            'next': 'https://backend.example.org/api/projects/?page=2',
            'results': [{'code': 'A', 'name': 'Project A', 'public': True, 'users': ['alice']}],
        })
        page2 = _mock_response({
            'next': None,
            'results': [
                {'code': 'B', 'name': 'Project B', 'public': False, 'users': ['alice', 'bob']},
            ],
        })
        mock_get.side_effect = [page1, page2]

        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            call_command('sync_projects')

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(Project.objects.count(), 2)

        project_a = Project.objects.get(code='A')
        self.assertEqual(project_a.name, 'Project A')
        self.assertTrue(project_a.public)
        self.assertEqual(set(project_a.users.values_list('username', flat=True)), {'alice'})

        project_b = Project.objects.get(code='B')
        self.assertFalse(project_b.public)
        self.assertEqual(
            set(project_b.users.values_list('username', flat=True)), {'alice', 'bob'}
        )

    @mock.patch('pyobs_archive.api.backend.requests.get')
    def test_updates_existing_project_and_drops_stale_member(self, mock_get):
        project = Project.objects.create(code='A', name='Old name', public=False)
        project.users.set([self.alice, self.bob])

        mock_get.return_value = _mock_response({
            'next': None,
            'results': [{'code': 'A', 'name': 'New name', 'public': True, 'users': ['alice']}],
        })

        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            call_command('sync_projects')

        project.refresh_from_db()
        self.assertEqual(project.name, 'New name')
        self.assertTrue(project.public)
        self.assertEqual(list(project.users.values_list('username', flat=True)), ['alice'])

    @mock.patch('pyobs_archive.api.backend.requests.get')
    def test_deletes_projects_removed_on_backend(self, mock_get):
        Project.objects.create(code='STALE', name='Stale', public=False)
        mock_get.return_value = _mock_response({'next': None, 'results': []})

        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            call_command('sync_projects')

        self.assertFalse(Project.objects.filter(code='STALE').exists())

    def test_aborts_when_backend_not_configured(self):
        with self.settings(ROBOTIC_BACKEND_URL='', ROBOTIC_BACKEND_TOKEN=''):
            with self.assertRaises(CommandError):
                call_command('sync_projects')
        self.assertEqual(Project.objects.count(), 0)

    @mock.patch('pyobs_archive.api.backend.requests.get')
    def test_aborts_with_nonzero_exit_when_backend_unreachable(self, mock_get):
        mock_get.side_effect = requests.ConnectionError('boom')

        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            with self.assertRaises(CommandError):
                call_command('sync_projects')
        self.assertEqual(Project.objects.count(), 0)

    @mock.patch('pyobs_archive.api.backend.requests.get')
    def test_aborts_when_backend_returns_server_error(self, mock_get):
        mock_get.return_value = _mock_response({}, status_code=502)

        with self.settings(ROBOTIC_BACKEND_URL='https://backend.example.org',
                            ROBOTIC_BACKEND_TOKEN='tok'):
            with self.assertRaises(CommandError):
                call_command('sync_projects')
        self.assertEqual(Project.objects.count(), 0)
