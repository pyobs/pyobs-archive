import math
import logging
import subprocess
from urllib.parse import urljoin
import os
import io
from astropy.io import fits
from astropy.time import Time

from django.db import models
from django.conf import settings
from django.utils.timezone import make_aware

from pyobs_archive.api.utils import FilenameFormatter

log = logging.getLogger(__name__)


class Frame(models.Model):
    """A single image."""
    basename = models.CharField('Name of file', max_length=50, db_index=True)
    path = models.CharField('Path to file', max_length=100)
    SITEID = models.CharField('Site of observation', max_length=10, db_index=True)
    TELID = models.CharField('Telescope used for observation', max_length=5, db_index=True)
    INSTRUME = models.CharField('Instrument used for observation', max_length=5, db_index=True)
    IMAGETYP = models.CharField('Type of image', max_length=15, db_index=True)
    RLEVEL = models.IntegerField('Reduction level', default=0, db_index=True)
    DATE_OBS = models.DateTimeField('Time exposure started', db_index=True)
    night = models.DateField('Night of observation', db_index=True)
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
    related = models.ManyToManyField("self", symmetrical=False)
    REQNUM = models.CharField('Unique number for request', max_length=30, null=True, default=None)

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
        self.night = header['DAY-OBS']

        # binning
        if 'XBINNING' in header and 'YBINNING' in header:
            self.XBINNING = header['XBINNING']
            self.YBINNING = header['YBINNING']
        else:
            log.warning('Missing or invalid XBINNING and/or YBINNING in FITS header.')

        # keywords to copy
        keywords = ['SITEID', 'TELID', 'INSTRUME',
                    'TEL-RA', 'TEL-DEC', 'TEL-ALT', 'TEL-AZ', 'TEL-FOCU',
                    'SUNALT', 'SUNDIST', 'MOONALT', 'MOONDIST', 'MOONFRAC',
                    'IMAGETYP', 'XORGSUBF', 'YORGSUBF', 'OBJECT', 'EXPTIME',
                    'FILTER', 'DATAMEAN', 'REQNUM']
        for k in keywords:
            self._set_header(header, k)

        # image size and offset
        self.width = header['NAXIS1']
        self.height = header['NAXIS2']

        # add filename
        self.basename = header['FNAME']

        # position vector
        if self.TEL_RA is not None and self.TEL_DEC is not None:
            ra = math.radians(self.TEL_RA)
            dec = math.radians(self.TEL_DEC)
            self.vec_x = math.cos(dec) * math.cos(ra)
            self.vec_y = math.cos(dec) * math.sin(ra)
            self.vec_z = math.sin(dec)

        # reduction level
        self.RLEVEL = header['RLEVEL'] if 'RLEVEL' in header else 0

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
        info = {k: getattr(self, k) for k in ['id', 'basename', 'SITEID', 'TELID', 'INSTRUME', 'RLEVEL',
                                              'DATE_OBS', 'FILTER', 'OBJECT', 'EXPTIME', 'RLEVEL']}

        # add obstype
        info['OBSTYPE'] = self.IMAGETYP

        # add binning
        info['binning'] = '%dx%d' % (self.XBINNING, self.YBINNING)

        # remove OBJECT and FILTER for BIAS and DARKs
        if self.IMAGETYP in ['bias', 'dark']:
            info['OBJECT'] = None
            info['FILTER'] = None

        # add related frames
        info['related_frames'] = [f.id for f in self.related.all()]

        # add url
        info['url'] = urljoin(settings.HTTP_ROOT, urljoin(settings.ROOT_URL, 'frames/%d/download/' % self.id))

        # finished
        return info

    def link_related(self, header):
        """Link related images.

        Args:
            header (Header): FITS header to take data from.
        """

        # collect filenames
        basenames = []
        for key, value in header.items():
            if key.startswith('L1AVG') or key in ['L1BIAS', 'L1DARK', 'L1FLAT', 'L1RAW']:
                basenames.append(value)

        # link frames
        frames = []
        for name in basenames:
            try:
                f = Frame.objects.get(basename=name)
                frames.append(f)
            except Frame.DoesNotExist:
                log.error('Could not set related frames, %s not found.', name)
        self.related.set(frames)

    @staticmethod
    def ingest(filename):
        # create path and filename formatter
        if hasattr(settings, 'PATH_FORMATTER') and settings.PATH_FORMATTER is not None:
            path_fmt = FilenameFormatter(settings.PATH_FORMATTER)
        else:
            raise ValueError('No path formatter configured.')
        filename_fmt = None
        if hasattr(settings, 'FILENAME_FORMATTER') and settings.FILENAME_FORMATTER is not None:
            filename_fmt = FilenameFormatter(settings.FILENAME_FORMATTER)

        # get archive root
        root = settings.ARCHIVE_ROOT

        # open file
        fits_file = fits.open(filename)

        # get path for archive
        path = path_fmt(fits_file['SCI'].header)

        # get filename for archive
        if isinstance(filename_fmt, FilenameFormatter):
            name = filename_fmt(fits_file['SCI'].header)
        else:
            tmp = fits_file['SCI'].header['FNAME']
            name = os.path.basename(tmp[:tmp.find('.')])

        # create new filename and set it in header
        out_filename = name + '.fits.fz'
        fits_file['SCI'].header['FNAME'] = name

        # find or create image
        if Frame.objects.filter(basename=name).exists():
            img = Frame.objects.get(basename=name)
        else:
            img = Frame(basename=name)

        # set headers
        img.path = path
        img.add_fits_header(fits_file['SCI'].header)

        # write to database
        img.save()

        # link related
        img.link_related(fits_file['SCI'].header)

        # create path if necessary
        file_path = os.path.join(root, path)
        if not os.path.exists(file_path):
            os.makedirs(file_path)

        # write FITS file to byte stream and close
        with io.BytesIO() as bio:
            fits_file.writeto(bio)
            fits_file.close()

            # pipe data into fpack
            log.info('Fpacking file...')
            proc = subprocess.Popen(['/usr/bin/fpack', '-S', '-'],
                                    stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                    stdout=open(os.path.join(file_path, out_filename), 'wb'))
            proc.communicate(bytes(bio.getbuffer()))

            # all good store it
            if proc.returncode == 0:
                log.info('Stored image as %s...', img.basename)
                return img.basename
            else:
                raise ValueError('Could not fpack file %s.' % filename)
