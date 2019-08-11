import json

from django.shortcuts import render

# Create your views here.

from django.http import HttpResponse, JsonResponse
from django.template import loader

from pyobs_archive.archive.models import Image


def index(request):
    template = loader.get_template('archive/index.html')
    context = {}
    return HttpResponse(template.render(context, request))


def images(request):
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
