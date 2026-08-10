from django.db import migrations

from pyobs_archive.authentication.crypto import _fernet


def encrypt_existing_tokens(apps, schema_editor):
    Profile = apps.get_model('authentication', 'Profile')
    for profile in Profile.objects.all():
        updates = {}
        if profile.access_token:
            updates['access_token'] = _fernet().encrypt(profile.access_token.encode()).decode()
        if profile.refresh_token:
            updates['refresh_token'] = _fernet().encrypt(profile.refresh_token.encode()).decode()
        if updates:
            Profile.objects.filter(pk=profile.pk).update(**updates)


def decrypt_existing_tokens(apps, schema_editor):
    Profile = apps.get_model('authentication', 'Profile')
    for profile in Profile.objects.all():
        updates = {}
        if profile.access_token:
            updates['access_token'] = _fernet().decrypt(profile.access_token.encode()).decode()
        if profile.refresh_token:
            updates['refresh_token'] = _fernet().decrypt(profile.refresh_token.encode()).decode()
        if updates:
            Profile.objects.filter(pk=profile.pk).update(**updates)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_widen_profile_tokens'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_tokens, decrypt_existing_tokens),
    ]
