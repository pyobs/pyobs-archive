import requests
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header


class RemoteToken:
    @property
    def key(self):
        return "key"

    @property
    def user(self):
        return "user"


class RemoteTokenAuthentication(BaseAuthentication):
    keyword = 'Token'

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            msg = 'Invalid token header. No credentials provided.'
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = 'Invalid token header. Token string should not contain spaces.'
            raise exceptions.AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeError:
            msg = 'Invalid token header. Token string should not contain invalid characters.'
            raise exceptions.AuthenticationFailed(msg)

        return self.authenticate_credentials(token)

    def authenticate_credentials(self, key):
        # call portal
        res = requests.get('https://observe.monet.uni-goettingen.de/api/profile/',
                           headers={'Authorization': 'Token ' + key})

        # check
        response = res.json()
        if 'username' in response:
            # get or create user
            from django.contrib.auth.models import User
            user, _ = User.objects.get_or_create(username=response['username'])
        else:
            raise exceptions.AuthenticationFailed('Invalid token.')

        if not user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        return user, key

    def authenticate_header(self, request):
        return self.keyword
