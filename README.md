pyobs-archive
=============

A webservice for an archive for astronomical images. Implements most of the interfaces
defined by [Las Cumbres Observatory](https://developers.lco.global/#archive).

Quick start
-----------

Clone the repository:

    https://github.com/pyobs/pyobs-archive.git
    cd pytel-archive
    
Run the Docker containers:

    docker-compose up -d
    
After it is running, get a shell inside the container:

    docker exec -it pyobs-archive_web_1 /bin/bash
    
Inside, run migrate:

    python manage.py migrate
    
And create a superuser for yourself:

    python manager.py createsuperuser
    
Create another user for ingesting new images (in this case, we call it "pyobs") and create the token 
that must be used when sending new images:

    python manager.py createsuperuser
    python manage.py drf_create_token pyobs

Now you can open a browser at http://localhost:8000/ and log in to the homepage.

Used packages
-------------
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
- [Font Awesome](https://fontawesome.com/) for icons.
- [webpack](https://webpack.js.org/) for bundling all resources.

Thanks
------
Thanks to all the people at [LCO](https://lco.global/) for their support. This project also uses
some JavaScript from [their archive](https://archive.lco.global/).
