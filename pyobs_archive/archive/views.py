from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from astropy.io import fits
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
        # create filename formatter
        ff = FilenameFormatter('{TELESCOP|lower}/{DAY-OBS|date:}/raw/{TELESCOP|lower}_{DAY-OBS|date:}_{IMAGETYP}.fits')

        # loop all incoming files
        filenames = []
        for key in request.FILES:
            # open file
            f = fits.open(request.FILES[key])

            # create image and set fits headers
            img = Image()
            img.add_fits_header(f[0].header)

            # get filename in archive
            img.filename = ff(f[0].header)
            filenames.append(img.filename)

            # write to database
            img.save()
            log.info('Stored image as %s...', img.filename)

            # close file
            f.close()

        return JsonResponse({'created': len(filenames), 'filenames': filenames})
