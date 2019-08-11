from django.db import models


class Telescope(models.Model):
    """A telescope."""
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Instrument(models.Model):
    """An instrument."""
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=50)
    telescope = models.ForeignKey(Telescope, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class Image(models.Model):
    """A single image."""
    filename = models.CharField('Name of file', max_length=50)
    telescope = models.ForeignKey(Telescope, on_delete=models.CASCADE)
    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE)
    image_type = models.CharField('Type of image', max_length=10)
    reduction_level = models.IntegerField('Reduction level', default=0)
    date_obs = models.DateTimeField('Time exposure started')
    target = models.CharField('Name of target', max_length=50)
    vec_x = models.FloatField('Telescope RA/Dec position as vector, X component')
    vec_y = models.FloatField('Telescope RA/Dec position as vector, Y component')
    vec_z = models.FloatField('Telescope RA/Dec position as vector, Z component')
    tel_ra = models.FloatField('Telescope Right Ascension', null=True)
    tel_dec = models.FloatField('Telescope Declination', null=True)
    tel_alt = models.FloatField('Altitude of telescope at start of exposure')
    tel_az = models.FloatField('Azimuth of telescope at start of exposure')
    tel_focus = models.FloatField('Focus of telescope')
    sol_alt = models.FloatField('Elevation of sun above horizon in deg')
    moon_alt = models.FloatField('Elevation of moon above horizon in deg')
    moon_ill = models.FloatField('Illuminated fraction of moon surface')
    moon_sep = models.FloatField('Ok-sky distance of object to Moon in deg')
    exp_time = models.FloatField('Exposure time')
    filter = models.CharField('Filter used', max_length=20)
    binning = models.IntegerField('Binning of image', default=1)
    offset_x = models.IntegerField('X offset of image in unbinned pixels', default=0)
    offset_y = models.IntegerField('Y offset of image in unbinned pixels', default=0)
    width = models.IntegerField('Width of image in binned pixels')
    height = models.IntegerField('Height of image in binned pixels')
    data_mean = models.FloatField('Mean data value')
    quality = models.FloatField('Estimation of image quality (0..1)')
