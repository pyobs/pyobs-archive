pyobs-archive
#############

*pyobs-archive* is a stand-alone archive for FITS images. It provides a general look & feel and a
REST API similar to the one used by the `LCO archive <https://developers.lco.global/#archive>`_,
and (optionally) restricts frame access to project members via a pyobs-portal connection.

Screenshots
===========

The frame browser, with a filter sidebar and sortable, filterable table of frames:

.. image:: _static/screenshots/frame-list.jpg
   :alt: Frame browser showing a filter sidebar and a sortable table of BIAS, DARK, SKYFLAT, and
         EXPOSE frames.
   :width: 100%

A frame's row expanded, showing its calibration/catalog frames and a live preview:

.. image:: _static/screenshots/frame-preview.jpg
   :alt: Expanded frame row with a FITS headers button and a rendered preview image of a
         star field.
   :width: 100%

.. toctree::
   :maxdepth: 1

   installation
   configuration
   architecture
   api
   development
