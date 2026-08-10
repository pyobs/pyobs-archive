from astropy.io import fits
from django.test import TestCase, RequestFactory

from pyobs_archive.api.models import Frame
from pyobs_archive.api.views import filter_frames


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
