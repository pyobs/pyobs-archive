import math

from astropy.time import Time
from django.db import models
import logging

from django.utils.timezone import make_aware

log = logging.getLogger(__name__)


class Image(models.Model):
    """A single image."""
    basename = models.CharField('Name of file', max_length=50)
    path = models.CharField('Path to file', max_length=100)
    SITEID = models.CharField('Site of observation', max_length=5)
    TELID = models.CharField('Telescope used for observation', max_length=5)
    INSTRUME = models.CharField('Instrument used for observation', max_length=5)
    IMAGETYP = models.CharField('Type of image', max_length=10)
    RLEVEL = models.IntegerField('Reduction level', default=0)
    DATE_OBS = models.DateTimeField('Time exposure started')
    OBJECT = models.CharField('Name of Object', max_length=50, null=True, default=None)
    TEL_RA = models.FloatField('Telescope Right Ascension', null=True)
    TEL_DEC = models.FloatField('Telescope Declination', null=True)
    TEL_ALT = models.FloatField('Altitude of telescope at start of exposure', null=True, default=None)
    TEL_AZ = models.FloatField('Azimuth of telescope at start of exposure', null=True, default=None)
    TEL_FOCU = models.FloatField('Focus of telescope', null=True, default=None)
    SUNALT = models.FloatField('Elevation of sun above horizon in deg', null=True, default=None)
    SUNDIST = models.FloatField('Ok-sky distance of object to Sun in deg', null=True, default=None)
    MOONALT = models.FloatField('Elevation of moon above horizon in deg', null=True, default=None)
    MOONFRAC = models.FloatField('Illuminated fraction of moon surface', null=True, default=None)
    MOONDIST = models.FloatField('Ok-sky distance of object to Moon in deg', null=True, default=None)
    EXPTIME = models.FloatField('Exposure time')
    FILTER = models.CharField('Filter used', max_length=20, null=True, default=None)
    binning = models.IntegerField('Binning of image', default=1)
    XORGSUBF = models.IntegerField('X offset of image in unbinned pixels', default=0)
    YORGSUBF = models.IntegerField('Y offset of image in unbinned pixels', default=0)
    width = models.IntegerField('Width of image in binned pixels')
    height = models.IntegerField('Height of image in binned pixels')
    DATAMEAN = models.FloatField('Mean data value')

    def __str__(self):
        return self.name

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
            setattr(self, keyword, header[keyword])
