# Generated by Django 2.2.4 on 2020-01-30 19:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_frame_reqnum'),
    ]

    operations = [
        migrations.AlterField(
            model_name='frame',
            name='IMAGETYP',
            field=models.CharField(db_index=True, max_length=15, verbose_name='Type of image'),
        ),
    ]