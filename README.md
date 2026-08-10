# pyobs-archive

A webservice for an archive for astronomical images. Implements most of the interfaces
defined by [Las Cumbres Observatory](https://developers.lco.global/#archive).

## Configuration

All settings are controlled by environment variables. Copy `pyobs_archive/local_settings.example.py` to
`pyobs_archive/local_settings.py` for local overrides, or set the following in your environment / `.env` file:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | dev-only fallback | Django secret key — **change in production** |
| `DEBUG` | `false` | Set to `true` for development |
| `ALLOWED_HOSTS` | (empty) | Comma-separated list of allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | (empty) | Comma-separated list of trusted origins |
| `CORS_ALLOWED_ORIGINS` | (empty) | Comma-separated list of origins allowed to make cross-origin requests to the API |
| `SQL_ENGINE` | `django.db.backends.sqlite3` | Database backend |
| `SQL_DATABASE` | `db.sqlite3` | Database name / path |
| `SQL_USER` | `user` | Database user |
| `SQL_PASSWORD` | `password` | Database password |
| `SQL_HOST` | `localhost` | Database host |
| `SQL_PORT` | `5432` | Database port |
| `STATIC_ROOT` | `/static/` | Directory for collected static files |
| `ARCHIVE_ROOT` | `/data/` | Directory FITS files are stored in and served from |
| `PATH_FORMATTER` | `{SITEID}/{DAY-OBS}/` | Format string for the sub-path files are stored under, within `ARCHIVE_ROOT` |
| `FILENAME_FORMATTER` | (empty, use the header `FNAME`) | Format string for the archived filename |
| `DJANGO_LOG_LEVEL` | `INFO` | Log level for Django's logger |
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` | (empty) | OAuth login (optional) |
| `OAUTH_TOKEN_URL` / `OAUTH_PROFILE_URL` | `http://localhost/...` | OAuth login (optional) |

## Running

### Development

```bash
uv run manage.py migrate
uv run manage.py createsuperuser
uv run manage.py runserver
```

With no configuration at all, this runs against a local SQLite database. Open `http://localhost:8000/` and
log in with the superuser you created.

Create another user for ingesting new images (in this case, we call it "pyobs") and create the token
that must be used when sending new images:

    uv run manage.py createsuperuser
    uv run manage.py drf_create_token pyobs

### Docker Compose

A production-ready setup with PostgreSQL and nginx is provided in [`docker-compose.yaml`](docker-compose.yaml).
The application image is pulled from `ghcr.io/pyobs/pyobs/pyobs-archive:latest`. Copy
[`.env.example`](.env.example) to `.env` and [`nginx.conf.example`](nginx.conf.example) to `nginx.conf`, then
adjust the values — in particular, bind-mount your real FITS storage over the `archive_data` volume.

The UI is served by nginx on port **8098**.

```bash
docker compose up -d
docker compose exec web uv run manage.py createsuperuser        # yourself
docker compose exec web uv run manage.py createsuperuser        # e.g. "pyobs", for ingest
docker compose exec web uv run manage.py drf_create_token pyobs
```


## Changelog

#### version 1.0.0 (2020-11-23)
- Initial release

#### version 1.1.0 (2020-12-04)
- Added footer to page 

### version 1.1.1 (2020-12-10)
- Minor bugfix
 

## Used packages

The following packages are used in this project.

Python:
- [django](https://www.djangoproject.com/) for the whole project.
- [django REST framework](https://www.django-rest-framework.org/) for the web API.
- [astropy](https://www.astropy.org/) for astronomical calculations.
- [gunicorn](https://gunicorn.org/) for running the web server.

JavaScript, CSS & Co.:
- [jQuery](https://jquery.com/) for DOM access.
- [jQuery.fileDownload](https://github.com/johnculviner/jquery.fileDownload) for downloading files.
- [jQuery.typeWatch](https://github.com/dennyferra/TypeWatch) for handling user input.
- [Bootstrap](https://getbootstrap.com/) for the UI.
- [Bootstrap Table](https://bootstrap-table.com/) for showing the data as table.
- [Bootstrap Icons](https://icons.getbootstrap.com/) for icons.

Thanks
------
Thanks to all the people at [LCO](https://lco.global/) for their support. This project also uses
some JavaScript from [their archive](https://archive.lco.global/).
