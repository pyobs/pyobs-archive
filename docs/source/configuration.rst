Configuration
#############

All settings are controlled by environment variables (put them in ``.env`` for Docker Compose, or
copy ``pyobs_archive/local_settings.example.py`` to ``pyobs_archive/local_settings.py`` for local
overrides outside Docker).

``SECRET_KEY`` (default: dev-only fallback)
    Django secret key — **change in production**.

``DEBUG`` (default: ``false``)
    Set to ``true`` for development.

``ALLOWED_HOSTS`` (default: empty)
    Comma-separated list of allowed hosts.

``CSRF_TRUSTED_ORIGINS`` (default: empty)
    Comma-separated list of trusted origins.

``CORS_ALLOWED_ORIGINS`` (default: empty)
    Comma-separated list of origins allowed to make cross-origin requests to the API.

``SQL_ENGINE`` (default: ``django.db.backends.sqlite3``)
    Database backend.

``SQL_DATABASE`` (default: ``db.sqlite3``)
    Database name / path.

``SQL_USER`` (default: ``user``), ``SQL_PASSWORD`` (default: ``password``)
    Database credentials.

``SQL_HOST`` (default: ``localhost``), ``SQL_PORT`` (default: ``5432``)
    Database host/port.

``STATIC_ROOT`` (default: ``/static/``)
    Directory for collected static files.

``ARCHIVE_ROOT`` (default: ``/data/``)
    Directory FITS files are stored in and served from.

``PATH_FORMATTER`` (default: ``{SITEID}/{DAY-OBS}/``)
    Format string for the sub-path files are stored under, within ``ARCHIVE_ROOT``.

``FILENAME_FORMATTER`` (default: empty, use the header ``FNAME``)
    Format string for the archived filename.

``DJANGO_LOG_LEVEL`` (default: ``INFO``)
    Log level for Django's logger.

``KEYCLOAK_SERVER_URL`` (default: empty)
    Keycloak login — an optional addon on top of local Django username/password; unset disables
    it.

``KEYCLOAK_REALM`` (default: ``pyobs``)
    Keycloak realm.

``KEYCLOAK_CLIENT_ID`` / ``KEYCLOAK_CLIENT_SECRET`` (default: ``archive`` / empty)
    This service's Keycloak client credentials.

``KEYCLOAK_REDIRECT_URI`` (default: empty)
    Must match the redirect URI registered for this client in Keycloak.

``KEYCLOAK_IDP_HINT`` / ``KEYCLOAK_IDP_LABEL`` (default: empty)
    Optional one-click IdP login: hint passed to Keycloak as ``kc_idp_hint`` (skips its
    login/IdP-selection page) and the label for the login page's IdP button, e.g. ``gwdg`` /
    ``GWDG``.

``ADMIN_USERNAME`` / ``ADMIN_PASSWORD_HASH`` (default: empty)
    Settings-configured superuser, synced after every ``migrate``; leave unset to skip and use
    ``createsuperuser`` instead. Generate the hash with::

        uv run python -c "from django.contrib.auth.hashers import make_password; print(make_password('yourpassword'))"

``PORTAL_URL`` (default: empty)
    Base URL of pyobs-portal, used to mirror projects/members (``manage.py sync_projects``) and
    to resolve ``REQNUM`` to a project at ingest time. See :doc:`architecture`.

``PORTAL_TOKEN`` (default: empty)
    DRF token of a portal service account, used together with ``PORTAL_URL``.

``PORTAL_TIMEOUT`` (default: ``5``)
    Timeout in seconds for requests to the portal.

``PROJECT_ACCESS_CONTROL`` (default: ``false``)
    Restrict frame access to project members (+ public projects); unset/empty/``false`` keeps
    today's behavior (no access filtering).
