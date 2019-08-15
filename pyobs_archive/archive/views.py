import os
import logging
import zipfile
import datetime

from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.views.decorators.csrf import ensure_csrf_cookie
from astropy.io import fits
from django.conf import settings
from rest_framework.decorators import permission_classes, authentication_classes, api_view
from rest_framework.authentication import TokenAuthentication, SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from pyobs_archive.archive.models import Image
from pyobs_archive.archive.utils import FilenameFormatter


log = logging.getLogger(__name__)


@ensure_csrf_cookie
def index(request):
    template = loader.get_template('archive/index.html')
    return HttpResponse(template.render({}, request))


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAdminUser])
def create_view(request):
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
        if Image.objects.filter(basename=name).exists():
            img = Image.objects.get(basename=name)
        else:
            img = Image()

        # set headers
        img.path = path
        img.basename = name
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
        log.info('Stored image as %s...', img.basename)

    return JsonResponse({'created': len(filenames), 'filenames': filenames})


@api_view(['GET'])
@authentication_classes([TokenAuthentication, BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def frames(request):
    # get offset and limit
    offset = int(request.GET.get('offset', default=0))
    limit = int(request.GET.get('limit', default=10))

    # sort
    sort = request.GET.get('sort', default='DATE_OBS')
    order = request.GET.get('order', default='asc')
    sort_string = ('' if order == 'asc' else '-') + sort

    # get response
    data = Image.objects.order_by(sort_string)

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

    # get columns
    data = data.only('id', 'basename', 'IMAGETYP', 'SITEID', 'TELID', 'INSTRUME', 'RLEVEL', 'DATE_OBS', 'FILTER',
                     'OBJECT', 'EXPTIME', 'RLEVEL')

    # return them
    return JsonResponse({'total': len(data),
                         'totalNotFiltered': len(data),
                         'rows': list(data.values()[offset:offset + limit])})


@api_view(['GET'])
@authentication_classes([TokenAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def options(request):
    # get all options
    image_types = list(Image.objects.all().values_list('IMAGETYP', flat=True).distinct())
    sites = list(Image.objects.all().values_list('SITEID', flat=True).distinct())
    telescopes = list(Image.objects.all().values_list('TELID', flat=True).distinct())
    instruments = list(Image.objects.all().values_list('INSTRUME', flat=True).distinct())
    filters = list(Image.objects.all().values_list('FILTER', flat=True).distinct())

    # return all
    return JsonResponse({
        'imagetypes': image_types,
        'sites': sites,
        'telescopes': telescopes,
        'instruments': instruments,
        'filters': filters
    })


class PostAuthentication(TokenAuthentication):
    def authenticate(self, request):
        token = request.POST['auth_token']
        return self.authenticate_credentials(token)


@api_view(['POST'])
@authentication_classes([PostAuthentication])
@permission_classes([IsAuthenticated])
def zip(request):
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
        frame = Image.objects.get(id=frame_id)

        # get filename
        filename = os.path.join(root, frame.path, frame.basename + '.fits.fz')

        # add file to zip
        zip_file.write(filename, arcname=os.path.join(archive_name, os.path.basename(filename)))

    # return response
    response.set_cookie('fileDownload', 'true', path='/')
    response['Content-Disposition'] = 'attachment; filename={}'.format(archive_name + '.zip')
    return response
