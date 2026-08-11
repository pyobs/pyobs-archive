from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def pyobs_logo_light():
    # Deployments can point this at their own logo via settings/env; defaults to the
    # bundled pyobs logo (static/img/pyobs-logo-light.gif).
    return getattr(settings, "PYOBS_LOGO_LIGHT_URL", None) or static("img/pyobs-logo-light.gif")


@register.simple_tag
def pyobs_logo_dark():
    # Two variants because the wordmark's "py" is black - invisible on a dark sidebar
    # without a light-on-dark version to swap in.
    return getattr(settings, "PYOBS_LOGO_DARK_URL", None) or static("img/pyobs-logo-dark.gif")
