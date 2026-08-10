from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='access_token',
            field=models.TextField(default=''),
        ),
        migrations.AlterField(
            model_name='profile',
            name='refresh_token',
            field=models.TextField(default=''),
        ),
    ]
