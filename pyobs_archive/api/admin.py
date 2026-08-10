from django.contrib import admin
from .models import Frame


@admin.register(Frame)
class FrameAdmin(admin.ModelAdmin):
    list_display = ('basename', 'SITEID', 'TELID', 'INSTRUME', 'IMAGETYP', 'RLEVEL', 'DATE_OBS')
    list_filter = ('SITEID', 'TELID', 'INSTRUME', 'IMAGETYP', 'RLEVEL')
    search_fields = ('basename', 'OBJECT', 'REQNUM', 'OBSNUM')
