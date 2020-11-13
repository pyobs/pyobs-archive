"""pyobs_archive URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework.authentication import TokenAuthentication
if settings.TOKEN_AUTH == TokenAuthentication:
    from rest_framework.authtoken import views
else:
    from pyobs_archive.authentication import views

# get root url
root_url = settings.ROOT_URL
if root_url.startswith('/'):
    root_url = root_url[1:]

urlpatterns = [
    path(root_url, include('pyobs_archive.frontend.urls')),
    path(root_url + 'frames/', include('pyobs_archive.api.urls')),
    path(root_url + 'admin/', admin.site.urls),
    path(root_url + 'api-token-auth/', views.obtain_auth_token)
]
