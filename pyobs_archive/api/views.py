import os
import logging
import zipfile
import datetime
import math
import zipstream

from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
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
            name = Frame.ingest(request.FILES[key])
            filenames.append(name)
        except Exception as e:
            log.exception('Could not add image.')
            errors.append(str(e))

    # response
    res = {'created': len(filenames), 'filenames': filenames}
    if errors:
        res['errors'] = list(set(errors))
    return JsonResponse(res)


def filter_frames(data, request):
    # filter
    f = request.GET.get('IMAGETYPE', 'ALL')
    if f not in ['', 'ALL']:
        data = data.filter(IMAGETYP=f)
    f = request.GET.get('binning', 'ALL')
    if f not in ['', 'ALL']:
        b = f.split('x')
        data = data.filter(XBINNING=float(b[0]), YBINNING=float(b[1]))
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
        data = data.filter(RLEVEL=int(f))
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
    if len(start) > 0:
        data = data.filter(DATE_OBS__gte=start)
    end = request.GET.get('end', '').strip()
    if len(end) > 0:
        data = data.filter(DATE_OBS__lte=end)

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
        data = data.annotate(dist=(vec_x - F('vec_x')) ** 2 + (vec_y - F('vec_y')) ** 2 + (vec_z - F('vec_z')) ** 2)

        # apply filter (10' squared = 0.02778 (deg²)
        data = data.filter(dist__lte=0.02778)

    # finished
    return data


@api_view(['GET'])
@authentication_classes([TokenAuthentication, BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def frames_view(request):
    # get offset and limit
    offset = request.GET.get('offset', default=None)
    limit = request.GET.get('limit', default=None)

    # sort
    sort = request.GET.get('sort', default='DATE_OBS')
    order = request.GET.get('order', default='asc')
    sort_string = ('' if order == 'asc' else '-') + sort

    # get response
    data = Frame.objects.order_by(sort_string)

    # filter
    data = filter_frames(data, request)

    # get results
    if offset is None or limit is None:
        results = [frame.get_info() for frame in data]
    else:
        results = [frame.get_info() for frame in data[int(offset):int(offset) + int(limit)]]

    # return them
    return JsonResponse({'count': len(data),
                         'results': results})


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def aggregate_view(request):
    # get response
    data = Frame.objects

    # filter
    data = filter_frames(data, request).all()

    # get all options
    image_types = list(data.values_list('IMAGETYP', flat=True).distinct())
    sites = list(data.values_list('SITEID', flat=True).distinct())
    telescopes = list(data.values_list('TELID', flat=True).distinct())
    instruments = list(data.values_list('INSTRUME', flat=True).distinct())
    filters = list(data.values_list('FILTER', flat=True).distinct())
    binning = list(data.values_list('XBINNING', 'YBINNING').distinct())

    # return all
    return JsonResponse({
        'imagetypes': sorted(image_types),
        'sites': sorted(sites),
        'telescopes': sorted(telescopes),
        'instruments': sorted(instruments),
        'filters': sorted(filters),
        'binnings': sorted(['%dx%d' % b for b in binning])
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
    filename = os.path.join(root, frame.path, frame.basename + '.fits.fz')

    # send it
    with open(filename, 'rb') as fh:
        response = HttpResponse(fh.read(), content_type="image/fits")
        response.set_cookie('fileDownload', 'true', path='/')
        response['Content-Disposition'] = 'attachment; filename={}.fits.fz'.format(frame.basename)
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
    # get archive root
    root = settings.ARCHIV_SETTINGS['ARCHIVE_ROOT']

    # get name for archive
    archive_name = 'pyobsdata-' + datetime.datetime.now().strftime('%Y%m%d')

    # create zip file
    zip_file = zipstream.ZipFile()

    # add files
    for frame_id in request.POST.getlist('frame_ids[]'):
        # get frame
        frame = Frame.objects.get(id=frame_id)

        # get filename
        filename = os.path.join(root, frame.path, frame.basename + '.fits.fz')

        # add file to zip
        zip_file.write(filename, arcname=os.path.join(archive_name, os.path.basename(filename)))

    # create and return response
    response = StreamingHttpResponse(zip_file, content_type='application/zip')
    response.set_cookie('fileDownload', 'true', path='/')
    response['Content-Disposition'] = 'attachment; filename={}'.format(archive_name + '.zip')
    return response
