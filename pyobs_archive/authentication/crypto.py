import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """A TextField that transparently encrypts its value at rest, keyed off SECRET_KEY."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return _fernet().decrypt(value.encode()).decode()
