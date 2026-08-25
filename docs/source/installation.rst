Installation
############

Docker Compose is the supported way to run *pyobs-archive* in production. A ready-to-use
`docker-compose.yaml <https://github.com/pyobs/pyobs-archive/blob/develop/docker-compose.yaml>`_
is provided in the repository root, running two services:

- **web** — the app itself (``ghcr.io/pyobs/pyobs/pyobs-archive:latest``), migrating, collecting
  static files, and serving via gunicorn. Static files are served directly by gunicorn through
  `Whitenoise <https://whitenoise.readthedocs.io/>`_, so no separate web server container is
  needed — put this behind your own reverse proxy for TLS termination. Served on port **8098**.
- **db** — PostgreSQL.

Setup::

    git clone https://github.com/pyobs/pyobs-archive.git
    cd pyobs-archive
    cp .env.example .env
    # edit .env: at minimum SECRET_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, POSTGRES_*
    docker compose up -d

Bind-mount your real FITS storage over the ``archive_data`` volume in ``docker-compose.yaml``
instead of using the named volume, for production use.

Once it's up, create the users you need::

    docker compose exec web uv run manage.py createsuperuser        # yourself, for the admin UI
    docker compose exec web uv run manage.py createsuperuser        # e.g. "pyobs", for ingest
    docker compose exec web uv run manage.py drf_create_token pyobs

See :doc:`configuration` for every setting ``.env`` can carry, and :doc:`development` for running
it locally without Docker.
