from django.contrib import admin
from .models import Telescope, Instrument, Image

admin.site.register(Telescope)
admin.site.register(Instrument)
admin.site.register(Image)
