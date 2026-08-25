Development
###########

Running locally, without Docker::

    git clone https://github.com/pyobs/pyobs-archive.git
    cd pyobs-archive
    uv run manage.py migrate
    uv run manage.py createsuperuser
    uv run manage.py runserver

With no configuration at all, this runs against a local SQLite database. Open
``http://localhost:8000/`` and log in with the superuser you created.

Setting ``ADMIN_USERNAME``/``ADMIN_PASSWORD_HASH`` (see :doc:`configuration`) syncs a matching
superuser automatically after every ``migrate``, skipping the interactive ``createsuperuser`` step
— handy for scripted/Docker deployments.

Create another user for ingesting new images (called ``pyobs`` here) and the token it needs to
send new images (see :doc:`api`)::

    uv run manage.py createsuperuser
    uv run manage.py drf_create_token pyobs

Tests::

    uv run manage.py test
