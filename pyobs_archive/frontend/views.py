import logging

from django.conf import settings
from django.shortcuts import redirect
from django.views.decorators.csrf import ensure_csrf_cookie
from django.shortcuts import render


log = logging.getLogger(__name__)


@ensure_csrf_cookie
def index(request):
    # not logged in?
    if not request.user.is_authenticated:
        return redirect('%s?next=%s' % (settings.LOGIN_URL, request.path))

    # render
    return render(request, 'archive/index.html', {'user': request.user})
