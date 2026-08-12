from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
import logging

from pyobs_archive.authentication.crypto import EncryptedTextField

logger = logging.getLogger(__name__)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    access_token = EncryptedTextField(default='')
    refresh_token = EncryptedTextField(default='')
    # Keycloak's `sub` claim - the join key for pyobs-auth's USER_RESOLVER, not username/email
    # (those can change; `sub` doesn't). See pyobs-core's shared-auth design doc.
    keycloak_sub = models.CharField(max_length=255, unique=True, null=True, blank=True)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)
