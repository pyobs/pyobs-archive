from django.conf import settings


def keycloak(request):
    """Whether Keycloak login is configured - see PYOBS_AUTH in settings.py.

    Keycloak is an optional addon on top of local Django username/password login, not a
    replacement, so templates shouldn't show a login button for it unless it's actually set up.
    """
    return {"keycloak_login_enabled": bool(getattr(settings, "PYOBS_AUTH", {}).get("SERVER_URL"))}
