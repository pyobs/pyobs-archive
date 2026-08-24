import math
import logging
import subprocess
import time
from urllib.parse import urljoin
import os
import io
from astropy.io import fits
from astropy.time import Time

from django.db import models
from django.conf import settings
from django.utils.timezone import make_aware

from pyobs_archive.api.utils import FilenameFormatter
from pyobs_archive.api.backend import BackendClient, BackendUnavailable

log = logging.getLogger(__name__)

# In-process cache for the REQNUM (task id) -> project code map used by
# Frame.resolve_project_from_reqnum() (see specs/plans/2026-08-20-archive-project-access-control.md,
# D4). A short TTL keeps a burst of ingests (e.g. overnight) from triggering a full paginated
# `get_tasks()` fetch per frame, while still picking up new tasks reasonably quickly.
_TASK_MAP_CACHE_TTL = 60  # seconds
_task_map_cache = None
_task_map_cache_expires = 0.0


def _reset_task_map_cache():
    """Clear the in-process task map cache. Mainly a test hook."""
    global _task_map_cache, _task_map_cache_expires
    _task_map_cache = None
    _task_map_cache_expires = 0.0


def _get_task_map():
    """Fetch (and cache) REQNUM (task id) -> project code from the robotic backend.

    Raises:
        BackendUnavailable: if the backend can't be reached. Failures aren't cached, so the
            next call retries.
    """
    global _task_map_cache, _task_map_cache_expires

    now = time.monotonic()
    if _task_map_cache is not None and now < _task_map_cache_expires:
        return _task_map_cache

    client = BackendClient(
        settings.ROBOTIC_BACKEND_URL, settings.ROBOTIC_BACKEND_TOKEN,
        timeout=settings.ROBOTIC_BACKEND_TIMEOUT
    )
    tasks = client.get_tasks()

    task_map = {str(task['id']): task.get('project') for task in tasks}
    _task_map_cache = task_map
    _task_map_cache_expires = now + _TASK_MAP_CACHE_TTL
    return task_map


class Project(models.Model):
    """Local mirror of a pyobs-robotic-backend Project, kept up to date by the
    `sync_projects` management command (see specs/plans/2026-08-20-archive-project-access-control.md,
    §3). Used to decide which users may access frames of which project.
    """
    code = models.CharField('Project code', max_length=10, primary_key=True)
    name = models.CharField('Project name', max_length=200)
    public = models.BooleanField('Visible to every authenticated user', default=False)
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='projects', blank=True)

    def __str__(self):
        return self.code


class Frame(models.Model):
    """A single image."""
    basename = models.CharField('Name of file', max_length=50, unique=True)
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
    DATAMEAN = models.FloatField('Mean data value', null=True, default=None)
    related = models.ManyToManyField("self", symmetrical=False)
    REQNUM = models.CharField('Unique number for request', max_length=30, null=True, default=None)
    OBSNUM = models.CharField('Observation number (per-night)', max_length=30, null=True, default=None)
    PROJECT = models.CharField('Project code', max_length=10, null=True, default=None, db_index=True)

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
                    'FILTER', 'DATAMEAN', 'REQNUM', 'OBSNUM', 'PROJECT']
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

    def get_info(self, user=None):
        """Build the dict representation returned by the API.

        Args:
            user: requesting user, used to filter `related_frames` down to what they may access
                (see specs/plans/2026-08-20-archive-project-access-control.md, D10). No-op when
                `user` is None or `settings.PROJECT_ACCESS_CONTROL` is off.
        """
        # init info and copy some fields
        info = {k: getattr(self, k) for k in ['id', 'basename', 'SITEID', 'TELID', 'INSTRUME', 'RLEVEL',
                                              'DATE_OBS', 'FILTER', 'OBJECT', 'EXPTIME',
                                              'REQNUM', 'OBSNUM', 'PROJECT']}

        # add obstype
        info['OBSTYPE'] = self.IMAGETYP

        # add binning
        info['binning'] = '%dx%d' % (self.XBINNING, self.YBINNING)

        # remove OBJECT and FILTER for BIAS and DARKs
        if self.IMAGETYP in ['bias', 'dark']:
            info['OBJECT'] = None
            info['FILTER'] = None

        # add related frames, dropping any the requesting user can't access (D10)
        related = self.related.all()
        if user is not None and settings.PROJECT_ACCESS_CONTROL:
            from pyobs_archive.api.permissions import can_access_frame  # local: avoid import cycle
            related = [f for f in related if can_access_frame(user, f)]
        info['related_frames'] = [f.id for f in related]

        # add url
        info['url'] = 'frames/%d/download/' % self.id

        # finished
        return info

    def resolve_project_from_reqnum(self):
        """Resolve PROJECT via REQNUM -> Task.id -> project, using the robotic backend's task
        list, as a fallback for as long as the PROJECT FITS keyword isn't written upstream yet
        (see specs/plans/2026-08-20-archive-project-access-control.md, D4). No-op if PROJECT is
        already set, REQNUM is missing, or the backend isn't configured/reachable - in the
        latter case the frame simply stays unassociated (private, D5) and a warning is logged.
        """
        if self.PROJECT is not None or not self.REQNUM:
            return

        if not settings.ROBOTIC_BACKEND_URL or not settings.ROBOTIC_BACKEND_TOKEN:
            # Expected/common state for any install that hasn't configured the backend
            # connection (or the whole feature) yet - not worth a warning-level log per frame.
            log.info(
                'Cannot resolve PROJECT for REQNUM=%s: ROBOTIC_BACKEND_URL/ROBOTIC_BACKEND_TOKEN '
                'not configured.', self.REQNUM
            )
            return

        try:
            task_map = _get_task_map()
        except BackendUnavailable as e:
            log.warning('Could not resolve PROJECT for REQNUM=%s: %s', self.REQNUM, e)
            return

        self.PROJECT = task_map.get(str(self.REQNUM))

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
        log.info('Opening new file to ingest...')
        fits_file = fits.open(filename)

        # get path for archive
        path = path_fmt(fits_file['SCI'].header)

        # get filename for archive
        if isinstance(filename_fmt, FilenameFormatter):
            name = filename_fmt(fits_file['SCI'].header)
        else:
            tmp = os.path.basename(fits_file['SCI'].header['FNAME'])
            name = tmp[:tmp.find('.')] if '.' in tmp else tmp
        log.info('Formatted filename to %s.', name)

        # PATH_FORMATTER/FILENAME_FORMATTER pull their values from the FITS header, so make sure
        # neither can push the file outside of ARCHIVE_ROOT (via "..", an absolute path, or a
        # separator hiding in a header value)
        if not name or os.path.basename(name) != name or name in ('.', '..'):
            raise ValueError('Invalid filename derived from FITS header: %r' % name)
        archive_root = os.path.realpath(root)
        file_path = os.path.realpath(os.path.join(archive_root, path))
        if os.path.commonpath([archive_root, file_path]) != archive_root:
            raise ValueError('Formatted path escapes ARCHIVE_ROOT: %r' % path)

        # create new filename and set it in header
        out_filename = name + '.fits.fz'
        fits_file['SCI'].header['FNAME'] = name

        # find or create image
        img = Frame.objects.filter(basename=name).first() or Frame(basename=name)

        # set headers
        img.path = path
        img.add_fits_header(fits_file['SCI'].header)

        # fall back to REQNUM -> project resolution until the PROJECT FITS keyword is written
        # upstream (see specs/plans/2026-08-20-archive-project-access-control.md, D4)
        img.resolve_project_from_reqnum()

        # write to database
        log.info('Writing to database...')
        img.save()

        # link related
        img.link_related(fits_file['SCI'].header)

        # create path if necessary
        if not os.path.exists(file_path):
            os.makedirs(file_path)

        # write FITS file to byte stream and close
        with io.BytesIO() as bio:
            log.info('Writing file to buffer...')
            fits_file.writeto(bio)
            fits_file.close()
            buffer = bytes(bio.getbuffer())
            log.info(f"Wrote {len(buffer)} bytes.")

        # pipe data into fpack
        log.info('Fpacking file...')
        proc = subprocess.Popen(['/usr/bin/fpack', '-S', '-'],
                                stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE)
        data, _ = proc.communicate(buffer)
        log.info(f"Packed file into {len(data)} bytes.")

        # write file
        with open(os.path.join(file_path, out_filename), 'wb') as f:
            f.write(data)

        # all good store it
        if proc.returncode == 0:
            log.info('Stored image as %s...', out_filename)
            return img.basename
        else:
            raise ValueError('Could not fpack file %s.' % filename)

    @property
    def filename(self):
        root = settings.ARCHIVE_ROOT
        return os.path.join(root, self.path, self.basename + '.fits.fz')

    def delete_file(self):
        # delete file
        if os.path.exists(self.filename):
            os.remove(self.filename)

    def check_file(self) -> bool:
        # get filename
        filename = self.filename

        # does it exist?
        if not os.path.exists(filename):
            return False

        # check file size
        if os.path.getsize(filename) == 0:
            return False

        # try to get header
        try:
            fits.getheader(filename)
        except Exception:
            return False

        # all good
        return True
