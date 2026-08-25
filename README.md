# pyobs-archive

A webservice for an archive for astronomical images. Implements most of the interfaces
defined by [Las Cumbres Observatory](https://developers.lco.global/#archive), and optionally
restricts frame access to project members via a [pyobs-portal](https://github.com/pyobs/pyobs-portal)
connection.

## Documentation

Full installation (Docker Compose), configuration (every environment variable), architecture
(how this fits into the rest of the pyobs fleet), and REST API reference: see
[`docs/source/`](docs/source/) (built with Sphinx — `cd docs && uv run --with sphinx --with sphinx-rtd-theme make html`).

## Development

```bash
git clone https://github.com/pyobs/pyobs-archive.git
cd pyobs-archive
uv run manage.py migrate
uv run manage.py createsuperuser
uv run manage.py runserver
uv run manage.py test
```

See [`docs/source/development.rst`](docs/source/development.rst) for the full local-dev flow, and
[`docs/source/installation.rst`](docs/source/installation.rst) for the Docker Compose production
setup.

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
