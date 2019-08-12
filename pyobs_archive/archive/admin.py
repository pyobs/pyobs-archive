from django.contrib import admin
from .models import Telescope, Instrument, Image, Site

admin.site.register(Site)
admin.site.register(Telescope)
admin.site.register(Instrument)
admin.site.register(Image)
