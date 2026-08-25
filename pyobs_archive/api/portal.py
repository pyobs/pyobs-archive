"""Client for the pyobs-portal API.

Used to learn projects, their members and their public flag (`sync_projects` management
command, §3 of specs/plans/2026-08-20-archive-project-access-control.md) and to resolve
`REQNUM` (task id) to a project code as a fallback association at ingest time until the
`PROJECT` FITS keyword is written upstream (§1/§4 of the same plan).
"""

import logging

import requests

log = logging.getLogger(__name__)


class PortalUnavailable(Exception):
    """Raised when the portal cannot be reached or returns a server error."""


class PortalClient:
    """Thin wrapper around the pyobs-portal REST API."""

    # Hard cap on pages followed for a paginated endpoint, so a portal that keeps returning
    # "next" (buggy pagination, or a malicious/misbehaving server) can't loop forever.
    MAX_PAGES = 5000

    def __init__(self, base_url, token, timeout=5):
        """Create a new client.

        Args:
            base_url: Base URL of the portal, e.g. "https://portal.example.org".
            token: DRF token of a portal service account, sent as "Authorization: Token <token>".
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout

    def _headers(self):
        return {'Authorization': 'Token %s' % self.token}

    def _get(self, url):
        try:
            response = requests.get(url, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as e:
            raise PortalUnavailable('Could not reach portal at %s: %s' % (url, e)) from e

        if response.status_code >= 500:
            raise PortalUnavailable(
                'Portal returned status %d for %s' % (response.status_code, url)
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise PortalUnavailable('Portal request to %s failed: %s' % (url, e)) from e

        return response.json()

    def _get_all_pages(self, url):
        """Follow a DRF-paginated ("next") endpoint and return the concatenated results."""
        results = []
        pages = 0
        while url:
            pages += 1
            if pages > self.MAX_PAGES:
                raise PortalUnavailable(
                    'Portal returned more than %d pages for %s - aborting.'
                    % (self.MAX_PAGES, url)
                )

            data = self._get(url)
            if isinstance(data, dict):
                results.extend(data.get('results', []))
                url = data.get('next')
            else:
                results.extend(data)
                url = None
        return results

    def get_projects(self):
        """Fetch all accessible projects.

        Returns:
            List of dicts: {"code", "name", "public", "users": [username, ...]}.
        """
        return self._get_all_pages('%s/api/projects/' % self.base_url)

    def get_tasks(self):
        """Fetch all tasks (used for the REQNUM -> project fallback association).

        Returns:
            List of dicts: {"id", "project"}.
        """
        return self._get_all_pages('%s/api/tasks/' % self.base_url)
