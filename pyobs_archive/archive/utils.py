import logging
import re
from typing import Union
from astropy.io.fits import Header
from astropy.time import Time


log = logging.getLogger(__name__)


class FilenameFormatter:
    def __init__(self, fmt: Union[str, list], keys: dict = None):
        """Initializes a new filename formatter.

        Args:
            fmt: Filename format or list of formats. If list is given, first valid one is used.
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
        if not isinstance(self.format, list):
            self.format = [self.format]

        # loop formats
        for f in self.format:
            try:
                # find all placeholders in format
                placeholders = re.findall('\{[\w\d_-]+(?:\|[\w\d_-]+\:?(?:[\w\d_-]+)*)?\}', f)
                if len(placeholders) == 0:
                    return f

                # create output
                output = f

                # loop all placeholders
                for ph in placeholders:
                    # call method and replace
                    output = output.replace(ph, self._format_placeholder(ph, hdr))

                # finished
                return output

            except KeyError:
                # this format didn't work
                pass

        # still here?
        raise KeyError('No valid format found.')

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


__all__ = ['FilenameFormatter']
