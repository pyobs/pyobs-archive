REST API Reference
###################

Mounted under ``/frames/`` — similar in shape to the
`LCO archive API <https://developers.lco.global/#archive>`_.

Authentication
**************

Every request needs either a DRF token or a Keycloak Bearer token (if Keycloak is configured, see
:doc:`configuration`)::

    Authorization: Token <token>

A token is created with ``manage.py drf_create_token <username>`` (see :doc:`installation`), not
through a login endpoint. Read endpoints require any authenticated user (``IsAuthenticated``);
``create``/``delete`` require an admin/staff account (``IsAdminUser``).

Example::

    http https://archive.example.com/frames/?night=2020-02-01 "Authorization: Token 3d46d6b98edef947402e032e73eca7b54661c968"


List images
************

``GET /frames/`` — accepts HTTP GET parameters for filtering, e.g.::

    http https://archive.example.com/frames/?night=2020-02-01

for all images taken in the night of 1 Feb, 2020. Other filter parameters:

- ``IMAGETYPE`` — type of image (see `Filter options`_).
- ``binning`` — binning of image (see `Filter options`_).
- ``SITE``, ``TELESCOPE``, ``INSTRUMENT``, ``FILTER`` — see `Filter options`_.
- ``RLEVEL`` — reduction level (0=unreduced, 1=reduced).
- ``OBJECT`` — name of observed object.
- ``EXPTIME`` — exposure time in seconds.
- ``night`` — night of observation, ``yyyy-mm-dd``.
- ``basename`` — name of FITS file.
- ``REQNUM`` — request number from the robotic system.
- ``start`` / ``end`` — limit to images taken after/before this, isot format.
- ``RA`` / ``DEC`` — if both given, limit search to 10' around that position.
- ``limit`` / ``offset`` — pagination.
- ``order`` / ``asc`` — order results by this column, ascending if ``asc`` is given.


Filter options
**************

``GET /frames/aggregate/`` gives the possible choices for some of the filter parameters above::

    http https://archive.example.com/frames/aggregate/

Returns something like::

    {
        "binnings": ["1x1", "3x3"],
        "filters": ["B", "V", "R"],
        "imagetypes": ["bias", "dark", "object", "skyflat"],
        "instruments": ["instr1", "instr2"],
        "sites": ["Paranal", "Mauna Kea"],
        "telescopes": ["39m0", "30m0"]
    }


Single image
************

``GET /frames/<id>/`` — a single image's metadata.

- ``GET /frames/<id>/related/`` — related images.
- ``GET /frames/<id>/headers/`` — FITS headers, as JSON.
- ``GET /frames/<id>/preview/`` — a preview image.
- ``GET /frames/<id>/catalog/`` — the image's source catalog, if one exists.
- ``GET /frames/<id>/download/`` — download the FITS file, e.g. ``wget
  https://archive.example.com/frames/1000/download/``.
- ``DELETE /frames/<id>/delete/`` — delete the frame (admin only).


Downloading multiple images
****************************

``GET`` or ``POST /frames/zip/`` with a list of frame IDs downloads a zip of all of them, e.g.::

    wget https://archive.example.com/frames/zip/ --post-data="auth_token=<token>&frame_ids[]=1000&frame_ids[]=1001" -O data.zip

The auth token goes in the POST body here, and image IDs are given as ``frame_ids[]``.


Uploading images
*****************

``POST /frames/create/`` — admin/staff-only. Used by pyobs modules configured to archive their
FITS files here.
