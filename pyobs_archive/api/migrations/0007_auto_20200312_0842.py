# Generated by Django 2.2.4 on 2020-03-12 08:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_auto_20200130_1902'),
    ]

    operations = [
        migrations.AlterField(
            model_name='frame',
            name='REQNUM',
            field=models.CharField(default=None, max_length=30, null=True, verbose_name='Unique number for request'),
        ),
    ]
