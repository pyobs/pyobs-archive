from django.db import migrations

from pyobs_archive.authentication.crypto import EncryptedTextField


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_encrypt_existing_tokens'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='access_token',
            field=EncryptedTextField(default=''),
        ),
        migrations.AlterField(
            model_name='profile',
            name='refresh_token',
            field=EncryptedTextField(default=''),
        ),
    ]
