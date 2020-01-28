import logging
from rest_framework.response import Response
from rest_framework import parsers, renderers
from rest_framework.views import APIView

from pyobs_archive.authentication.serializers import AuthTokenSerializer

log = logging.getLogger(__name__)


class ObtainAuthToken(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser, parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']
        return Response({'token': token})


obtain_auth_token = ObtainAuthToken.as_view()
