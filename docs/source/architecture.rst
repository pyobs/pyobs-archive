Architecture
############

*pyobs-archive* is a stand-alone Django service, not a pyobs module — it has no
``pyobs-core`` dependency and isn't part of an XMPP fleet. It talks to the rest of the pyobs
ecosystem over HTTP:

- **Ingest** — pyobs modules that are configured to archive their FITS files send them to this
  service's REST API (see :doc:`api`, ``POST /frames/create/``), authenticated with a token
  created via ``manage.py drf_create_token``.
- **pyobs-portal** (optional) — with ``PORTAL_URL``/``PORTAL_TOKEN`` set, ``manage.py
  sync_projects`` periodically mirrors projects and their members/public flag from the portal
  into this service's local database, so per-request access checks (``PROJECT_ACCESS_CONTROL``)
  stay fast without a live call per request. The portal connection is also used to resolve a
  frame's ``REQNUM`` to a project at ingest time. See :doc:`configuration` for the connection
  settings.
- **Keycloak** (optional) — when ``KEYCLOAK_SERVER_URL`` is set, users can log in via Keycloak SSO
  (``/accounts/keycloak/``) alongside local Django username/password, and the REST API accepts a
  Keycloak Bearer token as an alternative to a DRF token (see :doc:`api`).
- **Clients** — anything reading images back out (web frontend, scripts, other services) talks to
  the same REST API.
