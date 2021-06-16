from django import template
from pyobs_archive.settings import LOGO_LINK

register = template.Library()


@register.simple_tag
def logolink():
    return LOGO_LINK
