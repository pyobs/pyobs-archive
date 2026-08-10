from django.contrib.auth.models import User
from pyobs_archive.authentication.models import Profile
from django.conf import settings
from rest_framework import authentication, exceptions
import requests


class OAuth2Backend(object):
    """
    Authenticate against the Oauth backend, using
    grant_type: password
    """

    def authenticate(self, request, username=None, password=None):
        response = requests.post(
            settings.OAUTH_CLIENT['TOKEN_URL'],
            data={
                'grant_type': 'password',
                'username': username,
                'password': password,
                'client_id': settings.OAUTH_CLIENT['CLIENT_ID'],
                'client_secret': settings.OAUTH_CLIENT['CLIENT_SECRET']
            }
        )
        if response.status_code == 200:
            user, _ = User.objects.get_or_create(username=username, defaults={'is_active': False})
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    'access_token': response.json()['access_token'],
                    'refresh_token': response.json()['refresh_token']
                }
            )
            if not user.is_active:
                return None
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None


class BearerAuthentication(authentication.BaseAuthentication):
    """
    Allows users to authenticate using the bearer token recieved from
    the odin auth server
    """
    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).split()
        if not auth_header or auth_header[0].lower() != b'bearer':
            return None
        if len(auth_header) != 2:
            raise exceptions.AuthenticationFailed('Invalid Authorization header')

        bearer = auth_header[1].decode()
        response = requests.get(
            settings.OAUTH_CLIENT['PROFILE_URL'],
            headers={'Authorization': 'Bearer {}'.format(bearer)}
        )

        if not response.status_code == 200:
            raise exceptions.AuthenticationFailed('No Such User')

        user, _ = User.objects.get_or_create(username=response.json()['email'], defaults={'is_active': False})
        Profile.objects.update_or_create(
            user=user,
            defaults={
                'access_token': bearer,
            }
        )
        if not user.is_active:
            raise exceptions.AuthenticationFailed('Account pending activation')
        return (user, None)
