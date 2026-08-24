"""Client for the pyobs-robotic-backend API.

Used to learn projects, their members and their public flag (`sync_projects` management
command, §3 of specs/plans/2026-08-20-archive-project-access-control.md) and to resolve
`REQNUM` (task id) to a project code as a fallback association at ingest time until the
`PROJECT` FITS keyword is written upstream (§1/§4 of the same plan).
"""

import logging

import requests

log = logging.getLogger(__name__)


class BackendUnavailable(Exception):
    """Raised when the robotic backend cannot be reached or returns a server error."""


class BackendClient:
    """Thin wrapper around the pyobs-robotic-backend REST API."""

    def __init__(self, base_url, token, timeout=5):
        """Create a new client.

        Args:
            base_url: Base URL of the backend, e.g. "https://backend.example.org".
            token: DRF token of a backend service account, sent as "Authorization: Token <token>".
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
            raise BackendUnavailable('Could not reach backend at %s: %s' % (url, e)) from e

        if response.status_code >= 500:
            raise BackendUnavailable(
                'Backend returned status %d for %s' % (response.status_code, url)
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise BackendUnavailable('Backend request to %s failed: %s' % (url, e)) from e

        return response.json()

    def _get_all_pages(self, url):
        """Follow a DRF-paginated ("next") endpoint and return the concatenated results."""
        results = []
        while url:
            data = self._get(url)
            results.extend(data.get('results', data if isinstance(data, list) else []))
            url = data.get('next') if isinstance(data, dict) else None
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
