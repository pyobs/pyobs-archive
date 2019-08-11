import json

from django.shortcuts import render

# Create your views here.

from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from astropy.io import fits
import io

from pyobs_archive.archive.models import Image


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
        print(response)
        return JsonResponse({'results': response})

    def post(self, request, *args, **kwargs):
        print("post")
        print(request.POST)
        print(request.FILES)
        #with io.StringIO(request.POST['image']) as bio:
        f = fits.open(request.FILES['image'])
        print(f[0].header)

        return JsonResponse({'created': 1})
