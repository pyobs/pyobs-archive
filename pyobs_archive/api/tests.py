import importlib
import io
import os
import tempfile
import zipfile
from unittest import mock

import requests
from astropy.io import fits
from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, RequestFactory
from rest_framework.exceptions import ParseError

import pyobs_archive.settings as archive_settings_module
from pyobs_archive.api import models as models_module
from pyobs_archive.api.portal import PortalClient, PortalUnavailable
from pyobs_archive.api.models import Frame, Project
from pyobs_archive.api.permissions import (
    accessible_projects, can_access_frame, filter_accessible_frames, frame_access_q,
)
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


def _make_frame(basename, **overrides):
    defaults = dict(
        path='p', SITEID='site1', TELID='tel1', INSTRUME='inst1',
        IMAGETYP='object', DATE_OBS='2024-01-15T10:00:00Z', night='2024-01-15',
        OBJECT='M31', EXPTIME=30.0, FILTER='clear', RLEVEL=0,
        XBINNING=1, YBINNING=1, width=100, height=100,
    )
    defaults.update(overrides)
    return Frame.objects.create(basename=basename, **defaults)


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


class AccessiblePermissionsTests(TestCase):
    """pyobs_archive.api.permissions: accessible_projects / can_access_frame / frame_access_q."""

    def setUp(self):
        self.member = User.objects.create_user('member')
        self.outsider = User.objects.create_user('outsider')
        self.staff = User.objects.create_user('staffer', is_staff=True)
        self.superuser = User.objects.create_superuser('admin', password='x')

        self.public_project = Project.objects.create(code='PUB', name='Public', public=True)
        self.private_project = Project.objects.create(code='PRIV', name='Private', public=False)
        self.private_project.users.set([self.member])
        Project.objects.create(code='OTHER', name='Other', public=False)

        self.frame_public = _make_frame('frame_public', PROJECT='PUB')
        self.frame_private = _make_frame('frame_private', PROJECT='PRIV')
        self.frame_other = _make_frame('frame_other', PROJECT='OTHER')
        self.frame_none = _make_frame('frame_none', PROJECT=None)

    def test_superuser_sees_everything(self):
        self.assertIsNone(accessible_projects(self.superuser))
        for frame in (self.frame_public, self.frame_private, self.frame_other, self.frame_none):
            self.assertTrue(can_access_frame(self.superuser, frame))

    def test_staff_sees_everything(self):
        self.assertIsNone(accessible_projects(self.staff))
        self.assertTrue(can_access_frame(self.staff, self.frame_none))

    def test_member_sees_member_and_public_projects(self):
        self.assertEqual(accessible_projects(self.member), {'PUB', 'PRIV'})
        self.assertTrue(can_access_frame(self.member, self.frame_public))
        self.assertTrue(can_access_frame(self.member, self.frame_private))
        self.assertFalse(can_access_frame(self.member, self.frame_other))

    def test_non_member_excluded_from_private_project(self):
        self.assertEqual(accessible_projects(self.outsider), {'PUB'})
        self.assertTrue(can_access_frame(self.outsider, self.frame_public))
        self.assertFalse(can_access_frame(self.outsider, self.frame_private))

    def test_unassociated_frame_is_superuser_only(self):
        self.assertFalse(can_access_frame(self.member, self.frame_none))
        self.assertFalse(can_access_frame(self.outsider, self.frame_none))
        self.assertTrue(can_access_frame(self.superuser, self.frame_none))

    def test_anonymous_user_has_no_access(self):
        anon = AnonymousUser()
        self.assertEqual(accessible_projects(anon), set())
        self.assertFalse(can_access_frame(anon, self.frame_public))

    def test_frame_access_q_filters_queryset_for_member(self):
        accessible = set(
            Frame.objects.filter(frame_access_q(self.member)).values_list('basename', flat=True)
        )
        self.assertEqual(accessible, {'frame_public', 'frame_private'})

    def test_frame_access_q_is_unfiltered_for_superuser(self):
        accessible = set(
            Frame.objects.filter(frame_access_q(self.superuser)).values_list('basename', flat=True)
        )
        self.assertEqual(
            accessible, {'frame_public', 'frame_private', 'frame_other', 'frame_none'}
        )

    def test_filter_accessible_frames_matches_can_access_frame_per_frame(self):
        frames = [self.frame_public, self.frame_private, self.frame_other, self.frame_none]

        result = {f.basename for f in filter_accessible_frames(self.member, frames)}
        self.assertEqual(result, {'frame_public', 'frame_private'})
        self.assertEqual(
            result, {f.basename for f in frames if can_access_frame(self.member, f)}
        )

    def test_filter_accessible_frames_is_unfiltered_for_superuser(self):
        frames = [self.frame_public, self.frame_private, self.frame_other, self.frame_none]
        result = filter_accessible_frames(self.superuser, frames)
        self.assertEqual(result, frames)

    def test_filter_accessible_frames_computes_accessible_projects_once(self):
        # the whole point of filter_accessible_frames() over calling can_access_frame() per
        # frame: one accessible_projects() computation (2 queries: public + member projects),
        # not one per frame
        frames = [self.frame_public, self.frame_private, self.frame_other, self.frame_none]
        with self.assertNumQueries(2):
            filter_accessible_frames(self.member, frames)


class FrameAccessEndpointTests(TestCase):
    """Endpoint-level access filtering (plan section 5) via the Django test client."""

    def setUp(self):
        self.member = User.objects.create_user('member', password='pw')
        self.outsider = User.objects.create_user('outsider', password='pw')
        self.superuser = User.objects.create_superuser('admin', password='pw')

        self.public_project = Project.objects.create(code='PUB', name='Public', public=True)
        self.private_project = Project.objects.create(code='PRIV', name='Private', public=False)
        self.private_project.users.set([self.member])

        self.archive_root = tempfile.mkdtemp()
        self.frame_public = self._make_frame_with_file('frame_public', PROJECT='PUB', SITEID='sitepub')
        self.frame_private = self._make_frame_with_file(
            'frame_private', PROJECT='PRIV', SITEID='sitepriv'
        )
        self.frame_none = self._make_frame_with_file('frame_none', PROJECT=None, SITEID='sitenone')

        # an accessible frame with an inaccessible related frame (D10)
        self.frame_public.related.set([self.frame_private])

    def _make_frame_with_file(self, basename, **overrides):
        frame = _make_frame(basename, **overrides)
        directory = os.path.join(self.archive_root, frame.path)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, frame.basename + '.fits.fz'), 'wb') as f:
            f.write(b'x')
        return frame

    def _zip_namelist(self, response):
        content = b''.join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return zf.namelist()

    # -- frames_view --------------------------------------------------------------------

    def test_frames_view_filters_to_accessible_when_flag_on(self):
        self.client.force_login(self.member)
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/')
        self.assertEqual(response.status_code, 200)
        basenames = {r['basename'] for r in response.json()['results']}
        self.assertEqual(basenames, {'frame_public', 'frame_private'})

    def test_frames_view_unfiltered_when_flag_off(self):
        # critical regression guard: default (flag off) behavior must stay identical
        self.client.force_login(self.outsider)
        response = self.client.get('/frames/')
        self.assertEqual(response.status_code, 200)
        basenames = {r['basename'] for r in response.json()['results']}
        self.assertEqual(basenames, {'frame_public', 'frame_private', 'frame_none'})

    # -- aggregate_view -------------------------------------------------------------------

    def test_aggregate_view_reflects_only_accessible_subset(self):
        self.client.force_login(self.outsider)  # only sees frame_public
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/aggregate/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sites'], ['sitepub'])

    def test_aggregate_view_unfiltered_when_flag_off(self):
        self.client.force_login(self.outsider)
        response = self.client.get('/frames/aggregate/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()['sites']), {'sitepub', 'sitepriv', 'sitenone'})

    # -- zip_view_get / zip_view_post ------------------------------------------------------

    def test_zip_view_get_only_includes_accessible_files(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.get('/frames/zip/')
        names = self._zip_namelist(response)
        self.assertTrue(any('frame_public' in n for n in names))
        self.assertFalse(any('frame_private' in n for n in names))

    def test_zip_view_post_silently_skips_unauthorized_ids(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.post('/frames/zip/', {
                'frame_ids[]': [self.frame_public.id, self.frame_private.id],
            })
        self.assertEqual(response.status_code, 200)
        names = self._zip_namelist(response)
        self.assertTrue(any('frame_public' in n for n in names))
        self.assertFalse(any('frame_private' in n for n in names))

    def test_zip_view_post_404_for_missing_id_when_flag_off(self):
        # regression guard: nonexistent ids still fail the whole request when the flag is off
        self.client.force_login(self.outsider)
        response = self.client.post('/frames/zip/', {'frame_ids[]': [999999]})
        self.assertEqual(response.status_code, 404)

    def test_zip_view_post_404_for_missing_id_when_flag_on(self):
        # a nonexistent id must still fail the whole request when the flag is on too - it must
        # NOT be conflated with "exists but inaccessible" (which is silently skipped, D9) and
        # swallowed by the same except-Http404 branch
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.post('/frames/zip/', {
                'frame_ids[]': [self.frame_public.id, 999999],
            })
        self.assertEqual(response.status_code, 404)

    def test_zip_view_requires_authentication(self):
        # regression test for #47: zip_view wasn't wrapped in @api_view(...), so its
        # @permission_classes([IsAuthenticated]) decorator had no effect and anonymous requests
        # could reach it, unlike every other frame-exposing endpoint in this file
        response = self.client.get('/frames/zip/')
        self.assertEqual(response.status_code, 401)

        response = self.client.post('/frames/zip/', {'frame_ids[]': [self.frame_public.id]})
        self.assertEqual(response.status_code, 401)

    # -- per-frame endpoints: frame_view, download_view, headers_view, preview_view,
    #    catalog_view all share the central _frame() access check --------------------------

    def test_frame_view_404_for_inaccessible_frame(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/%d/' % self.frame_private.id)
        self.assertEqual(response.status_code, 404)

    def test_frame_view_ok_for_accessible_frame(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/%d/' % self.frame_public.id)
        self.assertEqual(response.status_code, 200)

    def test_frame_view_accessible_when_flag_off(self):
        # regression guard: no filtering at all when the flag is off
        self.client.force_login(self.outsider)
        response = self.client.get('/frames/%d/' % self.frame_private.id)
        self.assertEqual(response.status_code, 200)

    def test_download_view_404_for_inaccessible_frame(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.get('/frames/%d/download/' % self.frame_private.id)
        self.assertEqual(response.status_code, 404)

    def test_headers_view_404_for_inaccessible_frame(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.get('/frames/%d/headers/' % self.frame_private.id)
        self.assertEqual(response.status_code, 404)

    def test_preview_view_404_for_inaccessible_frame(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.get('/frames/%d/preview/' % self.frame_private.id)
        self.assertEqual(response.status_code, 404)

    def test_catalog_view_404_for_inaccessible_frame(self):
        self.client.force_login(self.outsider)
        with self.settings(PROJECT_ACCESS_CONTROL=True, ARCHIVE_ROOT=self.archive_root):
            response = self.client.get('/frames/%d/catalog/' % self.frame_private.id)
        self.assertEqual(response.status_code, 404)

    def test_unassociated_frame_is_superuser_only_via_endpoint(self):
        self.client.force_login(self.member)
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/%d/' % self.frame_none.id)
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.superuser)
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/%d/' % self.frame_none.id)
        self.assertEqual(response.status_code, 200)

    # -- related_view / get_info()['related_frames'] (D10) ---------------------------------

    def test_related_view_filters_inaccessible_related_frames(self):
        self.client.force_login(self.outsider)  # only sees frame_public
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            response = self.client.get('/frames/%d/related/' % self.frame_public.id)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()]
        self.assertNotIn(self.frame_private.id, ids)

    def test_related_view_unfiltered_when_flag_off(self):
        self.client.force_login(self.outsider)
        response = self.client.get('/frames/%d/related/' % self.frame_public.id)
        self.assertEqual(response.status_code, 200)
        ids = [r['id'] for r in response.json()]
        self.assertIn(self.frame_private.id, ids)

    def test_get_info_drops_inaccessible_related_frames_for_user(self):
        with self.settings(PROJECT_ACCESS_CONTROL=True):
            info = self.frame_public.get_info(self.outsider)
        self.assertNotIn(self.frame_private.id, info['related_frames'])

    def test_get_info_keeps_related_frames_without_a_user(self):
        # no request user (e.g. called outside a request context) -> no filtering, matches the
        # flag-off / no-op default
        info = self.frame_public.get_info()
        self.assertIn(self.frame_private.id, info['related_frames'])


class FrameProjectIngestTests(TestCase):
    """PROJECT association: FITS header, REQNUM->project fallback via the portal."""

    def setUp(self):
        # resolve_project_from_reqnum() caches the task map in-process (module-level, TTL-based)
        # so tests that expect a fresh PortalClient.get_tasks() call don't see a previous
        # test's cached result.
        models_module._reset_task_map_cache()
        self.addCleanup(models_module._reset_task_map_cache)

    def test_project_read_from_header(self):
        frame = Frame()
        frame.add_fits_header(_header(PROJECT='XYZ001'))
        self.assertEqual(frame.PROJECT, 'XYZ001')

    def test_project_defaults_to_none_when_absent(self):
        frame = Frame()
        frame.add_fits_header(_header())
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.PortalClient')
    def test_reqnum_fallback_resolves_project(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.return_value = [{'id': 12345, 'project': 'XYZ001'}]

        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            frame.resolve_project_from_reqnum()

        self.assertEqual(frame.PROJECT, 'XYZ001')
        mock_client_cls.assert_called_once_with(
            'https://portal.example.org', 'tok', timeout=mock.ANY
        )

    def test_reqnum_fallback_is_noop_when_project_already_set(self):
        frame = Frame()
        frame.add_fits_header(_header(PROJECT='ABC001', REQNUM='999'))
        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            frame.resolve_project_from_reqnum()
        self.assertEqual(frame.PROJECT, 'ABC001')

    def test_reqnum_fallback_is_noop_without_reqnum(self):
        header = _header()
        del header['REQNUM']

        frame = Frame()
        frame.add_fits_header(header)
        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            frame.resolve_project_from_reqnum()
        self.assertIsNone(frame.PROJECT)

    def test_portal_not_configured_leaves_project_none(self):
        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(PORTAL_URL='', PORTAL_TOKEN=''):
            frame.resolve_project_from_reqnum()  # should not raise
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.PortalClient')
    def test_portal_unavailable_leaves_project_none(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.side_effect = PortalUnavailable('boom')

        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            frame.resolve_project_from_reqnum()  # should not raise
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.PortalClient')
    def test_reqnum_not_in_task_map_leaves_project_none(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.return_value = [{'id': 1, 'project': 'OTHER'}]

        frame = Frame()
        frame.add_fits_header(_header(REQNUM='12345'))
        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            frame.resolve_project_from_reqnum()
        self.assertIsNone(frame.PROJECT)

    @mock.patch('pyobs_archive.api.models.PortalClient')
    def test_task_map_is_cached_across_frames(self, mock_client_cls):
        mock_client_cls.return_value.get_tasks.return_value = [
            {'id': 1, 'project': 'A'}, {'id': 2, 'project': 'B'},
        ]

        frame1 = Frame()
        frame1.add_fits_header(_header(REQNUM='1'))
        frame2 = Frame()
        frame2.add_fits_header(_header(REQNUM='2'))

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            frame1.resolve_project_from_reqnum()
            frame2.resolve_project_from_reqnum()

        self.assertEqual(frame1.PROJECT, 'A')
        self.assertEqual(frame2.PROJECT, 'B')
        # a burst of ingests shouldn't trigger a fresh get_tasks() fetch per frame
        mock_client_cls.return_value.get_tasks.assert_called_once()


def _mock_response(json_data, status_code=200):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


class PortalClientPaginationTests(TestCase):
    """PortalClient._get_all_pages: DRF-style {results, next} pages, bare-list responses, and
    the max-pages abort."""

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_follows_dict_pages_via_next(self, mock_get):
        page1 = _mock_response({
            'next': 'https://portal.example.org/api/projects/?page=2',
            'results': [{'code': 'A'}],
        })
        page2 = _mock_response({'next': None, 'results': [{'code': 'B'}]})
        mock_get.side_effect = [page1, page2]

        client = PortalClient('https://portal.example.org', 'tok')
        result = client.get_projects()

        self.assertEqual(result, [{'code': 'A'}, {'code': 'B'}])
        self.assertEqual(mock_get.call_count, 2)

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_follows_bare_list_response_without_crashing(self, mock_get):
        # a non-paginated endpoint (or a portal that returns a bare list) must not hit the
        # dict-only `.get(...)` branch
        mock_get.return_value = _mock_response([{'code': 'A'}, {'code': 'B'}])

        client = PortalClient('https://portal.example.org', 'tok')
        result = client.get_projects()

        self.assertEqual(result, [{'code': 'A'}, {'code': 'B'}])
        mock_get.assert_called_once()

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_aborts_after_max_pages(self, mock_get):
        mock_get.return_value = _mock_response({
            'next': 'https://portal.example.org/api/projects/?page=next', 'results': [],
        })

        client = PortalClient('https://portal.example.org', 'tok')
        client.MAX_PAGES = 3

        with self.assertRaises(PortalUnavailable):
            client.get_projects()
        self.assertEqual(mock_get.call_count, 3)


class SyncProjectsCommandTests(TestCase):
    """`manage.py sync_projects`: upserts + reconciles the local Project mirror."""

    def setUp(self):
        self.alice = User.objects.create_user('alice')
        self.bob = User.objects.create_user('bob')

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_creates_projects_and_reconciles_members_across_pages(self, mock_get):
        page1 = _mock_response({
            'next': 'https://portal.example.org/api/projects/?page=2',
            'results': [{'code': 'A', 'name': 'Project A', 'public': True, 'users': ['alice']}],
        })
        page2 = _mock_response({
            'next': None,
            'results': [
                {'code': 'B', 'name': 'Project B', 'public': False, 'users': ['alice', 'bob']},
            ],
        })
        mock_get.side_effect = [page1, page2]

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
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

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_updates_existing_project_and_drops_stale_member(self, mock_get):
        project = Project.objects.create(code='A', name='Old name', public=False)
        project.users.set([self.alice, self.bob])

        mock_get.return_value = _mock_response({
            'next': None,
            'results': [{'code': 'A', 'name': 'New name', 'public': True, 'users': ['alice']}],
        })

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            call_command('sync_projects')

        project.refresh_from_db()
        self.assertEqual(project.name, 'New name')
        self.assertTrue(project.public)
        self.assertEqual(list(project.users.values_list('username', flat=True)), ['alice'])

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_deletes_projects_missing_from_a_non_empty_response(self, mock_get):
        Project.objects.create(code='STALE', name='Stale', public=False)
        Project.objects.create(code='KEEP', name='Keep', public=False)
        mock_get.return_value = _mock_response({
            'next': None,
            'results': [{'code': 'KEEP', 'name': 'Keep', 'public': False, 'users': []}],
        })

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            call_command('sync_projects')

        self.assertFalse(Project.objects.filter(code='STALE').exists())
        self.assertTrue(Project.objects.filter(code='KEEP').exists())

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_empty_response_does_not_wipe_existing_mirror(self, mock_get):
        # An empty projects list from the portal is far more likely to indicate a problem
        # (misconfigured service account, transient bad response) than "every project was
        # deleted" - refuse to wipe a non-empty local mirror in that case (a stale mirror is
        # safer than an empty one, since PROJECT=None frames are superuser-only, D5).
        project = Project.objects.create(code='KEEP', name='Keep', public=True)
        project.users.set([self.alice])
        mock_get.return_value = _mock_response({'next': None, 'results': []})

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            with self.assertRaises(CommandError):
                call_command('sync_projects')

        project.refresh_from_db()
        self.assertEqual(list(project.users.values_list('username', flat=True)), ['alice'])

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_empty_response_is_fine_when_mirror_already_empty(self, mock_get):
        mock_get.return_value = _mock_response({'next': None, 'results': []})

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            call_command('sync_projects')  # should not raise

        self.assertEqual(Project.objects.count(), 0)

    def test_aborts_when_portal_not_configured(self):
        with self.settings(PORTAL_URL='', PORTAL_TOKEN=''):
            with self.assertRaises(CommandError):
                call_command('sync_projects')
        self.assertEqual(Project.objects.count(), 0)

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_aborts_with_nonzero_exit_when_portal_unreachable(self, mock_get):
        mock_get.side_effect = requests.ConnectionError('boom')

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            with self.assertRaises(CommandError):
                call_command('sync_projects')
        self.assertEqual(Project.objects.count(), 0)

    @mock.patch('pyobs_archive.api.portal.requests.get')
    def test_aborts_when_portal_returns_server_error(self, mock_get):
        mock_get.return_value = _mock_response({}, status_code=502)

        with self.settings(PORTAL_URL='https://portal.example.org',
                            PORTAL_TOKEN='tok'):
            with self.assertRaises(CommandError):
                call_command('sync_projects')
        self.assertEqual(Project.objects.count(), 0)


class PortalSettingsEnvFallbackTests(TestCase):
    """PORTAL_URL/PORTAL_TOKEN/PORTAL_TIMEOUT read as module-level `os.environ.get()` calls in
    settings.py, so `override_settings` can't exercise their env-var fallback logic (it patches
    attributes on the already-loaded settings object, after that logic already ran). Reload the
    module under a patched environment instead, and reload it again afterward so later tests see
    the real environment again."""

    def test_falls_back_to_legacy_env_vars_when_new_ones_are_unset(self):
        overrides = {
            'ROBOTIC_BACKEND_URL': 'https://legacy.example.org',
            'ROBOTIC_BACKEND_TOKEN': 'legacytok',
            'ROBOTIC_BACKEND_TIMEOUT': '7',
        }
        try:
            with mock.patch.dict(os.environ, overrides, clear=False):
                os.environ.pop('PORTAL_URL', None)
                os.environ.pop('PORTAL_TOKEN', None)
                os.environ.pop('PORTAL_TIMEOUT', None)
                reloaded = importlib.reload(archive_settings_module)
                self.assertEqual(reloaded.PORTAL_URL, 'https://legacy.example.org')
                self.assertEqual(reloaded.PORTAL_TOKEN, 'legacytok')
                self.assertEqual(reloaded.PORTAL_TIMEOUT, 7.0)
        finally:
            importlib.reload(archive_settings_module)

    def test_new_env_vars_take_precedence_over_legacy_ones(self):
        overrides = {
            'PORTAL_URL': 'https://new.example.org',
            'PORTAL_TOKEN': 'newtok',
            'PORTAL_TIMEOUT': '3',
            'ROBOTIC_BACKEND_URL': 'https://legacy.example.org',
            'ROBOTIC_BACKEND_TOKEN': 'legacytok',
            'ROBOTIC_BACKEND_TIMEOUT': '7',
        }
        try:
            with mock.patch.dict(os.environ, overrides, clear=False):
                reloaded = importlib.reload(archive_settings_module)
                self.assertEqual(reloaded.PORTAL_URL, 'https://new.example.org')
                self.assertEqual(reloaded.PORTAL_TOKEN, 'newtok')
                self.assertEqual(reloaded.PORTAL_TIMEOUT, 3.0)
        finally:
            importlib.reload(archive_settings_module)
