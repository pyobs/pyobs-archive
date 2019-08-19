import math
import logging
import urllib.parse
from astropy.time import Time

from django.db import models
from django.conf import settings
from django.utils.timezone import make_aware


log = logging.getLogger(__name__)


class Frame(models.Model):
    """A single image."""
    filename = models.CharField('Name of file', max_length=50, db_index=True)
    path = models.CharField('Path to file', max_length=100)
    SITEID = models.CharField('Site of observation', max_length=10, db_index=True)
    TELID = models.CharField('Telescope used for observation', max_length=5, db_index=True)
    INSTRUME = models.CharField('Instrument used for observation', max_length=5, db_index=True)
    IMAGETYP = models.CharField('Type of image', max_length=10, db_index=True)
    RLEVEL = models.IntegerField('Reduction level', default=0, db_index=True)
    DATE_OBS = models.DateTimeField('Time exposure started', db_index=True)
    OBJECT = models.CharField('Name of Object', max_length=50, null=True, default=None, db_index=True)
    TEL_RA = models.FloatField('Telescope Right Ascension', null=True)
    TEL_DEC = models.FloatField('Telescope Declination', null=True)
    vec_x = models.FloatField('Telescope orientation as vector, x component', null=True, db_index=True)
    vec_y = models.FloatField('Telescope orientation as vector, y component', null=True, db_index=True)
    vec_z = models.FloatField('Telescope orientation as vector, z component', null=True, db_index=True)
    TEL_ALT = models.FloatField('Altitude of telescope at start of exposure', null=True, default=None)
    TEL_AZ = models.FloatField('Azimuth of telescope at start of exposure', null=True, default=None)
    TEL_FOCU = models.FloatField('Focus of telescope', null=True, default=None)
    SUNALT = models.FloatField('Elevation of sun above horizon in deg', null=True, default=None)
    SUNDIST = models.FloatField('Ok-sky distance of object to Sun in deg', null=True, default=None)
    MOONALT = models.FloatField('Elevation of moon above horizon in deg', null=True, default=None)
    MOONFRAC = models.FloatField('Illuminated fraction of moon surface', null=True, default=None)
    MOONDIST = models.FloatField('Ok-sky distance of object to Moon in deg', null=True, default=None)
    EXPTIME = models.FloatField('Exposure time', db_index=True)
    FILTER = models.CharField('Filter used', max_length=20, null=True, default=None, db_index=True)
    XBINNING = models.IntegerField('Binning of image in X direction', default=1)
    YBINNING = models.IntegerField('Binning of image in Y direction', default=1)
    XORGSUBF = models.IntegerField('X offset of image in unbinned pixels', default=0)
    YORGSUBF = models.IntegerField('Y offset of image in unbinned pixels', default=0)
    width = models.IntegerField('Width of image in binned pixels')
    height = models.IntegerField('Height of image in binned pixels')
    DATAMEAN = models.FloatField('Mean data value', null=True, default=True)
    related = models.ManyToManyField("self")

    def __str__(self):
        return self.basename

    def add_fits_header(self, header):
        """Add properties from FITS headers.

        Args:
            header (Header): FITS header to take data from.
        """

        # dates
        if 'DATE-OBS' in header:
            self.DATE_OBS = make_aware(Time(header['DATE-OBS']).to_datetime())
        else:
            raise ValueError('Could not find DATE-OBS in FITS header.')

        # binning
        if 'XBINNING' in header and 'YBINNING' in header:
            self.binning = header['XBINNING']
            if header['XBINNING'] != header['YBINNING']:
                log.warning('Binning in X and Y differ, using one for X.')
        else:
            log.warning('Missing or invalid XBINNING and/or YBINNING in FITS header.')

        # keywords to copy
        keywords = ['SITEID', 'TELID', 'INSTRUME',
                    'TEL-RA', 'TEL-DEC', 'TEL-ALT', 'TEL-AZ', 'TEL-FOCU',
                    'SUNALT', 'SUNDIST', 'MOONALT', 'MOONDIST', 'MOONFRAC',
                    'IMAGETYP', 'XORGSUBF', 'YORGSUBF', 'OBJECT', 'EXPTIME', 'FILTER', 'DATAMEAN']
        for k in keywords:
            self._set_header(header, k)

        # image size and offset
        self.width = header['NAXIS1']
        self.height = header['NAXIS2']

        # add filename
        self.filename = header['FNAME']

        # position vector
        if self.TEL_RA is not None and self.TEL_DEC is not None:
            ra = math.radians(self.TEL_RA)
            dec = math.radians(self.TEL_DEC)
            self.vec_x = math.cos(dec) * math.cos(ra)
            self.vec_y = math.cos(dec) * math.sin(ra)
            self.vec_z = math.sin(dec)

    def _set_header(self, header, keyword):
        """Set the attribute of this object from the FITS header of the same name.

        Args:
            header: Header to take value from.
            keyword: Keyword to set.
        """

        # does keyword exist?
        if keyword in header:
            # change - to _
            attr = keyword.replace('-', '_') if '-' in keyword else keyword

            # set it
            setattr(self, attr, header[keyword])

    def get_info(self):
        # init info and copy some fields
        info = {k: getattr(self, k) for k in ['id', 'filename', 'SITEID', 'TELID', 'INSTRUME', 'RLEVEL',
                                              'DATE_OBS', 'FILTER', 'OBJECT', 'EXPTIME', 'RLEVEL']}

        # add basename
        info['basename'] = self.filename[:self.filename.find('.')]

        # add obstype
        info['OBSTYPE'] = self.IMAGETYP

        # add related frames
        info['related_frames'] = [f.id for f in self.related.all()]

        # add url
        root = settings.ARCHIV_SETTINGS['HTTP_ROOT']
        info['url'] = urllib.parse.urljoin(root, 'frames/%d/download/' % self.id)

        # finished
        return info
