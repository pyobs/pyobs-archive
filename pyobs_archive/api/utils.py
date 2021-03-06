import logging
import re
from astropy.io.fits import Header
from astropy.time import Time
import numpy as np


log = logging.getLogger(__name__)


class FilenameFormatter:
    def __init__(self, fmt: str, keys: dict = None):
        """Initializes a new filename formatter.

        Args:
            fmt: Filename format.
            keys: Additional keys to pass to the formatter.
        """
        self.format = fmt
        self.keys = {} if keys is None else keys

        # define functions
        self.funcs = {
            'lower': self._format_lower,
            'time': self._format_time,
            'date': self._format_date,
            'filter': self._format_filter,
            'string': self._format_string
        }

    def _value(self, hdr: Header, key: str):
        """Returns value for given key.

        Args:
            hdr: Header to take value from.
            key: Key to return value for.

        Returns:
            Value for given key.
        """

        # first check keys
        if key in self.keys:
            return self.keys[key]

        # then check header
        return hdr[key]

    def __call__(self, hdr: Header) -> str:
        """Formats a filename given a format template and a FITS header.

        Args:
            hdr: FITS header to take values from.

        Returns:
            Formatted filename.

        Raises:
            KeyError: If either keyword could not be found in header or method could not be found.
        """

        # make fmt a list
        if self.format is None:
            return None

        # create output
        output = self.format

        # find all placeholders in format
        placeholders = re.findall('\{[\w\d_-]+(?:\|[\w\d_-]+\:?(?:[\w\d_-]+)*)?\}', self.format)
        if len(placeholders) == 0:
            return self.format

        # loop all placeholders
        for ph in placeholders:
            # call method and replace
            output = output.replace(ph, self._format_placeholder(ph, hdr))

        # finished
        return output

    def _format_placeholder(self, placeholder: str, hdr: Header) -> str:
        """Format a given placeholder.

        Args:
            placeholder: Placeholder to format.
            hdr: FITS header to take values from.

        Returns:
            Formatted placeholder.

        Raises:
            KeyError: If method or FITS header keyword don't exist.
        """

        # remove curly brackets
        key = placeholder[1:-1]
        method = None
        params = []

        # do we have a pipe in here?
        if '|' in key:
            key, method = key.split('|')

        # parameters for method?
        if method is not None and ':' in method:
            method, *params = method.split(':')

        # if no method is given, just replace
        if method is None:
            return self._value(hdr, key)

        else:
            # get function (may raise KeyError)
            func = self.funcs[method]

            # call method and replace
            return func(hdr, key, *params)

    def _format_lower(self, hdr: Header, key: str) -> str:
        """Sets a given string to lowercase.

       Args:
           hdr: FITS header to take values from.
           key: The name of the FITS header key to use.

       Returns:
           Formatted string.
       """
        return self._value(hdr, key).lower()

    def _format_time(self, hdr: Header, key: str, delimiter: str = '-') -> str:
        """Formats time using the given delimiter.

       Args:
           hdr: FITS header to take values from.
           key: The name of the FITS header key to use.
           delimiter: Delimiter for time formatting.

       Returns:
           Formatted string.
       """
        fmt = '%H' + delimiter + '%M' + delimiter + '%S'
        date_obs = Time(self._value(hdr, key))
        return date_obs.datetime.strftime(fmt)

    def _format_date(self, hdr: Header, key: str, delimiter: str = '-') -> str:
        """Formats date using the given delimiter.

        Args:
            hdr: FITS header to take values from.
            key: The name of the FITS header key to use.
            delimiter: Delimiter for date formatting.

        Returns:
            Formatted string.
        """
        fmt = '%Y' + delimiter + '%m' + delimiter + '%d'
        date_obs = Time(self._value(hdr, key))
        return date_obs.datetime.strftime(fmt)

    def _format_filter(self, hdr: Header, key: str, image_type: str = 'IMAGETYP', prefix: str = '_') -> str:
        """Formats a filter, prefixed by a given separator, only if the image type requires it.

        Args:
            hdr: FITS header to take values from.
            key: The name of the FITS header key to use.
            image_type: FITS header key for IMAGETYP.
            prefix: Prefix to add to filter.

        Returns:
            Formatted string.
        """
        it = hdr[image_type].lower()
        if it in ['light', 'object', 'flat']:
            return prefix + self._value(hdr, key)
        else:
            return ''

    def _format_string(self, hdr: Header, key: str, format: str) -> str:
        """Formats a string using Python string substitution.

        Args:
            hdr: FITS header to take values from.
            key: The name of the FITS header key to use.
            format: A Python string format like %d, %05d, or %4.1f.

        Returns:
            Formatted string.
        """
        fmt = '%' + format
        return fmt % self._value(hdr, key)


def fitssec(hdu, keyword: str = 'TRIMSEC') -> np.ndarray:
    """Trim an image to TRIMSEC or BIASSEC.

    Args:
        hdu: HDU to take data from.
        keyword: Header keyword for section.

    Returns:
        Numpy array with image data.
    """

    # keyword not given?
    if keyword not in hdu.header:
        # return whole data
        return hdu.data

    # get value of section
    sec = hdu.header[keyword]

    # split values
    s = sec[1:-1].split(',')
    x = s[0].split(':')
    y = s[1].split(':')
    x0 = int(x[0]) - 1
    x1 = int(x[1])
    y0 = int(y[0]) - 1
    y1 = int(y[1])

    # return data
    return hdu.data[y0:y1, x0:x1]


__all__ = ['FilenameFormatter', 'fitssec']
