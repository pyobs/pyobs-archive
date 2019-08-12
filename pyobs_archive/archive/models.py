import math

from astropy.time import Time
from django.db import models
import logging

log = logging.getLogger(__name__)


class Site(models.Model):
    """A site."""
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Telescope(models.Model):
    """A telescope."""
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)
    site = models.ForeignKey(Site, on_delete=models.CASCADE)

    def __str__(self):
        return self.site.name + ' - ' + self.name


class Instrument(models.Model):
    """An instrument."""
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.code + ' - ' + self.name


class Image(models.Model):
    """A single image."""
    name = models.CharField('Name of file', max_length=50)
    path = models.CharField('Path to file', max_length=100)
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    telescope = models.ForeignKey(Telescope, on_delete=models.CASCADE)
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    image_type = models.CharField('Type of image', max_length=10)
    reduction_level = models.IntegerField('Reduction level', default=0)
    date_obs = models.DateTimeField('Time exposure started')
    target = models.CharField('Name of target', max_length=50, null=True, default=None)
    target_x = models.FloatField('Target position as vector, X component', null=True, default=None)
    target_y = models.FloatField('Target position as vector, Y component', null=True, default=None)
    target_z = models.FloatField('Target position as vector, Z component', null=True, default=None)
    tel_ra = models.FloatField('Telescope Right Ascension', null=True)
    tel_dec = models.FloatField('Telescope Declination', null=True)
    tel_alt = models.FloatField('Altitude of telescope at start of exposure', null=True, default=None)
    tel_az = models.FloatField('Azimuth of telescope at start of exposure', null=True, default=None)
    tel_focus = models.FloatField('Focus of telescope', null=True, default=None)
    sol_alt = models.FloatField('Elevation of sun above horizon in deg', null=True, default=None)
    moon_alt = models.FloatField('Elevation of moon above horizon in deg', null=True, default=None)
    moon_ill = models.FloatField('Illuminated fraction of moon surface', null=True, default=None)
    moon_sep = models.FloatField('Ok-sky distance of object to Moon in deg', null=True, default=None)
    exp_time = models.FloatField('Exposure time')
    filter = models.CharField('Filter used', max_length=20, null=True, default=None)
    binning = models.IntegerField('Binning of image', default=1)
    offset_x = models.IntegerField('X offset of image in unbinned pixels', default=0)
    offset_y = models.IntegerField('Y offset of image in unbinned pixels', default=0)
    width = models.IntegerField('Width of image in binned pixels')
    height = models.IntegerField('Height of image in binned pixels')
    data_mean = models.FloatField('Mean data value')

    def __str__(self):
        return self.name

    def add_fits_header(self, header):
        """Add properties from FITS headers.

        Args:
            header (Header): FITS header to take data from.
        """

        # dates
        if 'DATE-OBS' in header:
            self.date_obs = Time(header['DATE-OBS']).to_datetime()
        else:
            raise ValueError('Could not find DATE-OBS in FITS header.')

        # telescope and instrument
        self.site = Site.objects.get(code=header['SITEID'])
        self.telescope = Telescope.objects.get(code=header['TELID'])
        self.instrument = Instrument.objects.get(code=header['INSTRUME'])
        self.image_type = header['IMAGETYP'] if 'IMAGETYP' in header else None

        # binning
        if 'XBINNING' in header and 'YBINNING' in header:
            self.binning = header['XBINNING']
            if header['XBINNING'] != header['YBINNING']:
                log.warning('Binning in X and Y differ, using one for X.')
        else:
            log.warning('Missing or invalid XBINNING and/or YBINNING in FITS header.')

        # telescope stuff
        if 'OBJRA' in header and 'OBJDEC' in header:
            self.tel_ra = header['OBJRA']
            self.tel_dec = header['OBJDEC']
            ra = math.radians(header['OBJRA'])
            dec = math.radians(header['OBJDEC'])
            self.target_x = math.cos(dec) * math.cos(ra)
            self.target_y = math.cos(dec) * math.sin(ra)
            self.target_z = math.sin(dec)
        if 'TEL-ALT' in header and 'TEL-AZ' in header:
            self.tel_alt = header['TEL-ALT']
            self.tel_az = header['TEL-AZ']
        if 'TEL-FOCU' in header:
            self.tel_focus = header['TEL-FOCU']

        # environment
        if 'SOL-ALT' in header:
            self.sol_alt = header['SOL-ALT']
        if 'MOON-ALT' in header:
            self.moon_alt = header['MOON-ALT']
        if 'MOON-ILL' in header:
            self.moon_ill = header['MOON-ILL']
        if 'MOON-SEP' in header:
            self.moon_sep = header['MOON-SEP']

        # image size and offset
        self.width = header['NAXIS1']
        self.height = header['NAXIS2']
        self.offset_x = header['XORGSUBF'] if 'XORGSUBF' in header else 0
        self.offset_y = header['YORGSUBF'] if 'YORGSUBF' in header else 0

        # other stuff
        self.target = header['OBJECT'] if 'OBJECT' in header else None
        self.exp_time = header['EXPTIME']
        self.filter = header['FILTER'] if 'FILTER' in header else None
        self.data_mean = header['DATAMEAN']
