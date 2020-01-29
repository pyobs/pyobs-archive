import requests
from django.contrib.auth.models import User
from rest_framework import serializers


class AuthTokenSerializer(serializers.Serializer):
    username = serializers.CharField(label="Username")
    password = serializers.CharField(
        label="Password",
        style={'input_type': 'password'},
        trim_whitespace=False
    )

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            # call portal
            res = requests.post('https://observe.monet.uni-goettingen.de/api/api-token-auth/',
                                data={'username': username, 'password': password})

            # got a token?
            user = None
            response = res.json()
            if 'token' in response:
                # get or create user
                user, created = User.objects.get_or_create(username=username)

                # store it
                attrs['user'] = user
                attrs['token'] = response['token']

            # The authenticate call simply returns None for is_active=False
            # users. (Assuming the default ModelBackend authentication
            # backend.)
            if not user:
                msg = 'Unable to log in with provided credentials.'
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = 'Must include "username" and "password".'
            raise serializers.ValidationError(msg, code='authorization')

        return attrs
