import math
import logging
import subprocess
import shutil
import time
from urllib.parse import urljoin
import os
import io
from astropy.io import fits
from astropy.time import Time

from django.db import models
from django.conf import settings
from django.utils.timezone import make_aware

from pyobs_archive.api.ingest import publish_frame
from pyobs_archive.api.utils import FilenameFormatter
from pyobs_archive.api.portal import PortalClient, PortalUnavailable

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
    """Fetch (and cache) REQNUM (task id) -> project code from the portal.

    Raises:
        PortalUnavailable: if the portal can't be reached. Failures aren't cached, so the
            next call retries.
    """
    global _task_map_cache, _task_map_cache_expires

    now = time.monotonic()
    if _task_map_cache is not None and now < _task_map_cache_expires:
        return _task_map_cache

    client = PortalClient(
        settings.PORTAL_URL, settings.PORTAL_TOKEN,
        timeout=settings.PORTAL_TIMEOUT
    )
    tasks = client.get_tasks()

    task_map = {str(task['id']): task.get('project') for task in tasks}
    _task_map_cache = task_map
    _task_map_cache_expires = now + _TASK_MAP_CACHE_TTL
    return task_map


class Project(models.Model):
    """Local mirror of a pyobs-portal Project, kept up to date by the
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

        # add related frames, dropping any the requesting user can't access (D10). Computes
        # accessible_projects(user) once via filter_accessible_frames() rather than re-querying
        # it per related frame.
        related = self.related.all()
        if user is not None and settings.PROJECT_ACCESS_CONTROL:
            from pyobs_archive.api.permissions import filter_accessible_frames  # local: avoid import cycle
            related = filter_accessible_frames(user, related)
        info['related_frames'] = [f.id for f in related]

        # add url
        info['url'] = 'frames/%d/download/' % self.id

        # finished
        return info

    def resolve_project_from_reqnum(self):
        """Resolve PROJECT via REQNUM -> Task.id -> project, using the portal's task
        list, as a fallback for as long as the PROJECT FITS keyword isn't written upstream yet
        (see specs/plans/2026-08-20-archive-project-access-control.md, D4). No-op if PROJECT is
        already set, REQNUM is missing, or the portal isn't configured/reachable - in the
        latter case the frame simply stays unassociated (private, D5) and a warning is logged.
        """
        if self.PROJECT is not None or not self.REQNUM:
            return

        if not settings.PORTAL_URL or not settings.PORTAL_TOKEN:
            # Expected/common state for any install that hasn't configured the portal
            # connection (or the whole feature) yet - not worth a warning-level log per frame.
            log.info(
                'Cannot resolve PROJECT for REQNUM=%s: PORTAL_URL/PORTAL_TOKEN '
                'not configured.', self.REQNUM
            )
            return

        try:
            task_map = _get_task_map()
        except PortalUnavailable as e:
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

        # Prepare and compress before changing any persistent state.
        with fits.open(filename) as fits_file:
            path = path_fmt(fits_file['SCI'].header)
            if isinstance(filename_fmt, FilenameFormatter):
                name = filename_fmt(fits_file['SCI'].header)
            else:
                name = os.path.basename(fits_file['SCI'].header['FNAME']).split('.')[0]
            if not name or os.path.basename(name) != name or name in ('.', '..'):
                raise ValueError('Invalid filename derived from FITS header: %r' % name)
            archive_root = os.path.realpath(root)
            file_path = os.path.realpath(os.path.join(archive_root, path))
            if os.path.commonpath([archive_root, file_path]) != archive_root:
                raise ValueError('Formatted path escapes ARCHIVE_ROOT: %r' % path)

            executable = shutil.which('fpack')
            if executable is None:
                raise ValueError('fpack not found on the server process PATH; install CFITSIO '
                                 'and add its bin directory to PATH.')
            fits_file['SCI'].header['FNAME'] = name
            header = fits_file['SCI'].header.copy()
            with io.BytesIO() as bio:
                fits_file.writeto(bio)
                buffer = bio.getvalue()

        try:
            proc = subprocess.Popen([executable, '-S', '-'], stdin=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            data, stderr = proc.communicate(buffer)
        except OSError as exc:
            raise ValueError('Could not launch fpack at %s: %s' % (executable, exc)) from exc
        if proc.returncode:
            detail = stderr[:2000].decode('utf-8', errors='replace')
            raise ValueError('fpack exited with status %s: %s' % (proc.returncode, detail))
        if not data:
            raise ValueError('fpack returned empty output.')
        try:
            with fits.open(io.BytesIO(data)) as packed:
                packed.verify('exception')
                if packed['SCI'].data is None or packed['SCI'].data.size == 0:
                    raise ValueError('SCI contains no image data')
        except Exception as exc:
            raise ValueError('fpack returned invalid FITS image data: %s' % exc) from exc

        def update_frame():
            img = Frame.objects.select_for_update().filter(basename=name).first()
            old_filename = img.filename if img is not None else None
            if img is None:
                img = Frame(basename=name)
            img.path = path
            img.add_fits_header(header)
            img.resolve_project_from_reqnum()
            img.save()
            img.link_related(header)
            return old_filename

        publish_frame(archive_root, name, os.path.join(file_path, name + '.fits.fz'),
                      data, update_frame)
        log.info('Stored image as %s.', name)
        return name

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
