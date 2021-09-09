import io
import json
import os
import logging
import datetime
import math
import time

import numpy as np
import zipstream
from astropy.table import Table
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse, Http404
from astropy.io import fits
from django.conf import settings
from django.db.models import F
from rest_framework.decorators import permission_classes, api_view
from rest_framework.exceptions import ParseError
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from pyobs_archive.api.models import Frame
from pyobs_archive.api.utils import fitssec

log = logging.getLogger(__name__)


def _frame(frame_id):
    # get frame
    try:
        frame = Frame.objects.get(id=frame_id)
    except Frame.DoesNotExist:
        raise Http404()

    # build filename
    root = settings.ARCHIVE_ROOT
    filename = os.path.join(root, frame.path, frame.basename + '.fits.fz')

    # return both
    return frame, filename


@api_view(['POST'])
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


@api_view(['GET'])
@permission_classes([IsAdminUser])
def delete_view(request, frame_id):
    # get frame and filename
    frame, filename = _frame(frame_id)

    # delete file
    os.remove(filename)

    # delete DB entry
    frame.delete()

    # finished
    return HttpResponse()


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
    f = request.GET.get('FILTER', 'ALL')
    if f not in ['', 'ALL']:
        if f == 'None':
            f = None
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
    f = request.GET.get('night', '').strip()
    if f != '':
        data = data.filter(night=f)
    f = request.GET.get('basename', '').strip()
    if f != '':
        data = data.filter(basename__icontains=f)
    f = request.GET.get('REQNUM', '').strip()
    if f != '':
        data = data.filter(REQNUM=f)

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
@permission_classes([IsAuthenticated])
def frames_view(request):
    # get offset and limit
    try:
        offset = int(request.GET.get('offset', default=0))
        limit = int(request.GET.get('limit', default=1000))
    except ValueError:
        raise ParseError('Invalid values for offset/limit.')

    # limit to 1000
    limit = max(0, min(limit, 1000))
    offset = max(0, offset)

    # sort
    sort = request.GET.get('sort', default='DATE_OBS')
    order = request.GET.get('order', default='asc')
    sort_string = ('' if order == 'asc' else '-') + sort

    # get response
    data = Frame.objects.order_by(sort_string, 'id')

    # filter
    data = filter_frames(data, request)

    # get results
    results = [frame.get_info() for frame in data[int(offset):int(offset) + int(limit)]]

    # return them
    return JsonResponse({'count': data.count(), 'results': results})


@api_view(['GET'])
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

    # remove Nones
    filters = [(x or "None") for x in filters]

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
@permission_classes([IsAuthenticated])
def frame_view(request, frame_id):
    # get data
    frame, filename = _frame(frame_id)
    return JsonResponse(frame.get_info())


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_view(request, frame_id):
    # get frame and filename
    frame, filename = _frame(frame_id)

    # send it
    with open(filename, 'rb') as fh:
        response = HttpResponse(fh.read(), content_type="image/fits")
        response.set_cookie('fileDownload', 'true', path='/')
        response['Content-Disposition'] = 'attachment; filename={}.fits.fz'.format(frame.basename)
        return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def related_view(request, frame_id):
    # get frame
    frame, filename = _frame(frame_id)

    # get all related and return it
    related = [f.get_info() for f in frame.related.all()]
    return JsonResponse(related, safe=False)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def headers_view(request, frame_id):
    # get frame and filename
    frame, filename = _frame(frame_id)

    # load headers
    hdr = fits.getheader(filename, 'SCI')
    headers = [{'key': k, 'value': hdr[k]} for k in sorted(hdr.keys()) if k not in ['HISTORY', 'COMMENT', '']]

    # return them
    return JsonResponse({'results': headers})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def preview_view(request, frame_id):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    # get frame and filename
    frame, filename = _frame(frame_id)

    # load data and trim it
    hdus = fits.open(filename)
    data = fitssec(hdus['SCI'], 'TRIMSEC')
    hdus.close()

    # calculate cuts
    percent = 95
    sorted_data = sorted(data.flatten())
    n = int(len(sorted_data) * (1. - (percent / 100.)))
    cut = sorted_data[n:-n] if n > 0 else sorted_data
    vmin, vmax = np.min(cut), np.max(cut)

    # size
    width, height = 200, 200 / data.shape[1] * data.shape[0]

    # create figure
    dpi = 100
    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=dpi)
    fig.subplots_adjust(left=0, bottom=0, right=1, top=1)

    # draw image
    ax.imshow(data, vmin=vmin, vmax=vmax, cmap=cm.get_cmap('Greys_r'))

    # write to buffer and return it
    with io.BytesIO() as bio:
        fig.savefig(bio, format='png')
        return HttpResponse(bio.getvalue(), content_type="image/png")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def zip_view(request):
    # get archive root
    root = settings.ARCHIVE_ROOT

    # get name for archive
    archive_name = 'pyobsdata-' + datetime.datetime.now().strftime('%Y%m%d')

    # create zip file
    zip_file = zipstream.ZipFile()

    # add files
    for frame_id in request.POST.getlist('frame_ids[]'):
        # get frame
        frame, filename = _frame(frame_id)

        # add file to zip
        zip_file.write(filename, arcname=os.path.join(archive_name, os.path.basename(filename)))

    # create and return response
    response = StreamingHttpResponse(zip_file, content_type='application/zip')
    response.set_cookie('fileDownload', 'true', path='/')
    response['Content-Disposition'] = 'attachment; filename={}'.format(archive_name + '.zip')
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def catalog_view(request, frame_id):
    # get frame and filename
    frame, filename = _frame(frame_id)

    # load data and trim it
    try:
        cat = Table(fits.getdata(filename, 'CAT'))
    except KeyError:
        return HttpResponse('', content_type='text/comma-separated-values')
    except FileNotFoundError:
        raise Http404()

    # prepare response and send it
    with io.StringIO() as sio:
        # write table as CSV
        cat.write(sio, format='ascii', delimiter=',')

        # response
        return HttpResponse(sio.getvalue(), content_type='text/comma-separated-values')
