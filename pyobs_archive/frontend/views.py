import logging

from django.http import HttpResponse
from django.template import loader
from django.views.decorators.csrf import ensure_csrf_cookie


log = logging.getLogger(__name__)


@ensure_csrf_cookie
def index(request):
    template = loader.get_template('archive/index.html')
    return HttpResponse(template.render({}, request))
