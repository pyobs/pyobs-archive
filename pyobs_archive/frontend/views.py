import logging

from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.views.decorators.csrf import ensure_csrf_cookie


log = logging.getLogger(__name__)


@ensure_csrf_cookie
def index(request):
    # load template
    template = loader.get_template('archive/index.html')

    # is auth required?
    auth_required = settings.TOKEN_AUTH is not None

    # render
    return HttpResponse(template.render({'auth_required': auth_required, 'root_url': settings.ROOT_URL}, request))
