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
        latest_image_list = Image.objects.order_by('-date_obs')[:5]

        response = []
        for i in Image.objects.order_by('-date_obs')[:5]:
            response.append({
                'id': i.id,
                'filename': i.filename,
                'exp_time': i.exp_time
            })

        response = list(Image.objects.order_by('-date_obs').values())
        return JsonResponse({'results': response})

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
            f = fits.open(request.FILES[key])

            # get path for archive
            path = path_fmt(f[0].header)

            # get filename for archive
            if isinstance(filename_fmt, FilenameFormatter):
                name = filename_fmt(f[0].header)
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
            img.add_fits_header(f[0].header)

            # write to database
            img.save()

            # create path if necessary
            filename = os.path.join(root, path, name + '.fits.fz')
            file_path = os.path.dirname(filename)
            if not os.path.exists(file_path):
                os.makedirs(file_path)

            # write to disk
            gz = gzip.open(os.path.join(root, path, name + '.fits.gz'), 'wb')
            f.writeto(gz)
            gz.close()

            # close file
            f.close()
            log.info('Stored image as %s...', img.name)

        return JsonResponse({'created': len(filenames), 'filenames': filenames})
