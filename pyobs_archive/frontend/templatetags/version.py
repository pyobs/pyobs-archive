from django import template
from pyobs_archive.version import VERSION

register = template.Library()


@register.simple_tag
def version():
    return VERSION
