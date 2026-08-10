from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_auto_20200312_0842'),
    ]

    operations = [
        migrations.AddField(
            model_name='frame',
            name='OBSNUM',
            field=models.CharField(default=None, max_length=30, null=True, verbose_name='Observation number (per-night)'),
        ),
    ]
