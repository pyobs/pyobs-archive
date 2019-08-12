import gzip
import os

from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from astropy.io import fits
from django.conf import settings
import logging

from pyobs_archive.archive.models import Image
from pyobs_archive.archive.utils import FilenameFormatter

log = logging.getLogger(__name__)


@ensure_csrf_cookie
def index(request):
    template = loader.get_template('archive/index.html')
    context = {}
    return HttpResponse(template.render(context, request))


class ImagesController(View):
    def __init__(self, *args, **kwargs):
        View.__init__(self, *args, **kwargs)
        self.http_method_names = ['get', 'post']

    def get(self, request, *args, **kwargs):
        # get offset and limit
        offset = int(request.GET.get('offset', default=0))
        limit = int(request.GET.get('limit', default=10))

        # sort
        sort = request.GET.get('sort', default='date_obs')
        order = request.GET.get('order', default='asc')
        sort_string = ('' if order == 'asc' else '-') + sort

        # get response
        data = Image.objects.order_by(sort_string)

        # return them
        return JsonResponse({'total': len(data),
                             'totalNotFiltered': len(data),
                             'rows': list(data.values()[offset:offset + limit])})

    def post(self, request, *args, **kwargs):
        # create path and filename formatter
        if 'PATH_FORMATTER' in settings.ARCHIV_SETTINGS and settings.ARCHIV_SETTINGS['PATH_FORMATTER'] is not None:
            path_fmt = FilenameFormatter(settings.ARCHIV_SETTINGS['PATH_FORMATTER'])
        else:
            return JsonResponse({'error': 'No path formatter configured.'}, status=500)
        filename_fmt = None
        if 'FILENAME_FORMATTER' in settings.ARCHIV_SETTINGS and \
                settings.ARCHIV_SETTINGS['FILENAME_FORMATTER'] is not None:
            filename_fmt = FilenameFormatter(settings.ARCHIV_SETTINGS['FILENAME_FORMATTER'])

        # get archive root
        root = settings.ARCHIV_SETTINGS['ARCHIVE_ROOT']

        # loop all incoming files
        filenames = []
        for key in request.FILES:
            # open file
            fits_file = fits.open(request.FILES[key])

            # get path for archive
            path = path_fmt(fits_file['SCI'].header)

            # get filename for archive
            if isinstance(filename_fmt, FilenameFormatter):
                name = filename_fmt(fits_file['SCI'].header)
            else:
                tmp = request.FILES[key].name
                name = os.path.basename(tmp[:tmp.find('.')])

            # store it
            filenames.append(name)

            # find or create image
            if Image.objects.filter(name=name).exists():
                img = Image.objects.get(name=name)
            else:
                img = Image()

            # set headers
            img.path = path
            img.name = name
            img.add_fits_header(fits_file['SCI'].header)

            # write to database
            img.save()

            # loop all HDUs and convert to CompImageHDUs, if necessary/possible
            hdu_list = fits.HDUList()
            for i in fits_file:
                if type(fits_file[i]) in [fits.hdu.image.ImageHDU, fits.hdu.image.PrimaryHDU]:
                    # convert
                    hdu_list.append(fits.CompImageHDU(fits_file[i].data, fits_file[i].header))
                else:
                    # just copy
                    hdu_list.append(fits_file[i])

            # create path if necessary
            file_path = os.path.join(root, path)
            if not os.path.exists(file_path):
                os.makedirs(file_path)

            # write to disk
            hdu_list.writeto(os.path.join(file_path, name + '.fits.fz'), overwrite=True)

            # close file
            fits_file.close()
            log.info('Stored image as %s...', img.name)

        return JsonResponse({'created': len(filenames), 'filenames': filenames})
