import os
import logging
import subprocess
import zipfile
import datetime
import math
import io

from django.http import HttpResponse, JsonResponse
from astropy.io import fits
from django.conf import settings
from django.db.models import F
from rest_framework.decorators import permission_classes, authentication_classes, api_view
from rest_framework.authentication import TokenAuthentication, SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from pyobs_archive.api.models import Frame
from pyobs_archive.api.utils import FilenameFormatter


log = logging.getLogger(__name__)


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAdminUser])
def create_view(request):
    # loop all incoming files
    filenames = []
    errors = []
    for key in request.FILES:
        try:
            # ingest frame
            name = Frame.ingest(request.FILES[key], request.FILES[key].name)
            filenames.append(name)
        except Exception as e:
            log.exception('Could not add image.')
            errors.append(str(e))

    # response
    res = {'created': len(filenames), 'filenames': filenames}
    if errors:
        res['errors'] = list(set(errors))
    return JsonResponse(res)


@api_view(['GET'])
@authentication_classes([TokenAuthentication, BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def frames_view(request):
    # get offset and limit
    offset = int(request.GET.get('offset', default=0))
    limit = int(request.GET.get('limit', default=10))

    # sort
    sort = request.GET.get('sort', default='DATE_OBS')
    order = request.GET.get('order', default='asc')
    sort_string = ('' if order == 'asc' else '-') + sort

    # get response
    data = Frame.objects.order_by(sort_string)

    # filter
    f = request.GET.get('IMAGETYPE', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(IMAGETYP=f)
    f = request.GET.get('SITE', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(SITEID=f)
    f = request.GET.get('TELESCOPE', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(TELID=f)
    f = request.GET.get('INSTRUMENT', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(INSTRUME=f)
    f = request.GET.get('SITE', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(FILTER=f)
    f = request.GET.get('RLEVEL', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(RLEVEL=(0 if f == 'raw' else 1))
    f = request.GET.get('OBJECT', '').strip()
    if f != '':
        data = data.filter(OBJECT__icontains=f)
    f = request.GET.get('EXPTIME', '').strip()
    if f != '':
        data = data.filter(EXPTIME__gte=float(f))
    f = request.GET.get('basename', '').strip()
    if f != '':
        data = data.filter(filename__icontains=f)

    # date
    start = request.GET.get('start', '').strip()
    end = request.GET.get('end', '').strip()
    if len(start) > 0 and len(end) > 0:
        data=data.filter(DATE_OBS__range=(start, end))

    # position
    ra, dec = request.GET.get('RA', '').strip(), request.GET.get('DEC', '').strip()
    if ra != '' and dec != '':
        # calculate vector
        ra = math.radians(float(ra))
        dec = math.radians(float(dec))
        vec_x = math.cos(dec) * math.cos(ra)
        vec_y = math.cos(dec) * math.sin(ra)
        vec_z = math.sin(dec)

        # calculate dist
        data = data.annotate(dist=(vec_x-F('vec_x'))**2 + (vec_y-F('vec_y'))**2 + (vec_z-F('vec_z'))**2)

        # apply filter (10' squared = 0.02778 (deg²)
        data = data.filter(dist__lte=0.02778)

    # return them
    return JsonResponse({'total': len(data),
                         'totalNotFiltered': len(data),
                         'rows': [frame.get_info() for frame in data[offset:offset + limit]]})


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def aggregate_view(request):
    # get all options
    image_types = list(Frame.objects.all().values_list('IMAGETYP', flat=True).distinct())
    sites = list(Frame.objects.all().values_list('SITEID', flat=True).distinct())
    telescopes = list(Frame.objects.all().values_list('TELID', flat=True).distinct())
    instruments = list(Frame.objects.all().values_list('INSTRUME', flat=True).distinct())
    filters = list(Frame.objects.all().values_list('FILTER', flat=True).distinct())

    # return all
    return JsonResponse({
        'imagetypes': image_types,
        'sites': sites,
        'telescopes': telescopes,
        'instruments': instruments,
        'filters': filters
    })


@api_view(['GET'])
@authentication_classes([TokenAuthentication, BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def frame_view(request, frame_id):
    # get data
    data = Frame.objects.get(id=frame_id)
    return JsonResponse(data.get_info())


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def download_view(request, frame_id):
    # get frame and filename
    frame = Frame.objects.get(id=frame_id)
    root = settings.ARCHIV_SETTINGS['ARCHIVE_ROOT']
    filename = os.path.join(root, frame.path, frame.filename)

    # send it
    with open(filename, 'rb') as fh:
        response = HttpResponse(fh.read(), content_type="image/fits")
        response.set_cookie('fileDownload', 'true', path='/')
        response['Content-Disposition'] = 'attachment; filename={}'.format(frame.filename)
        return response


@api_view(['GET'])
@authentication_classes([TokenAuthentication, BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def related_view(request, frame_id):
    # get frame
    frame = Frame.objects.get(id=frame_id)

    # get all related and return it
    related = [f.get_info() for f in frame.related.all()]
    return JsonResponse(related, safe=False)


@api_view(['GET'])
@authentication_classes([TokenAuthentication, BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def headers_view(request, frame_id):
    # get frame and filename
    frame = Frame.objects.get(id=frame_id)
    root = settings.ARCHIV_SETTINGS['ARCHIVE_ROOT']
    filename = os.path.join(root, frame.path, frame.filename)

    # load headers
    hdr = fits.getheader(filename, 'SCI')
    headers = {k: hdr[k] for k in sorted(hdr.keys())}

    # return them
    return JsonResponse({'data': headers})


class PostAuthentication(TokenAuthentication):
    def authenticate(self, request):
        token = request.POST['auth_token']
        return self.authenticate_credentials(token)


@api_view(['POST'])
@authentication_classes([PostAuthentication])
@permission_classes([IsAuthenticated])
def zip_view(request):
    # create response
    response = HttpResponse(content_type='application/zip')

    # create zip file
    zip_file = zipfile.ZipFile(response, 'w')

    # get archive root
    root = settings.ARCHIV_SETTINGS['ARCHIVE_ROOT']

    # get name for archive
    archive_name = 'pyobsdata-' + datetime.datetime.now().strftime('%Y%m%d')

    # add files
    for frame_id in request.POST.getlist('frame_ids[]'):
        # get frame
        frame = Frame.objects.get(id=frame_id)

        # get filename
        filename = os.path.join(root, frame.path, frame.filename)

        # add file to zip
        zip_file.write(filename, arcname=os.path.join(archive_name, os.path.basename(filename)))

    # return response
    response.set_cookie('fileDownload', 'true', path='/')
    response['Content-Disposition'] = 'attachment; filename={}'.format(archive_name + '.zip')
    return response
