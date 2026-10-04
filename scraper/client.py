"""HTTP client for the Fluidtopics REST API.

Fluidtopics requires a session cookie obtained from the authentication endpoint
before any /api/khub/ calls will succeed. This client acquires that cookie
automatically on first use and then reuses it for all subsequent requests.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    # Identify ourselves politely; some servers reject requests without UA.
    "User-Agent": "docs-scraper/1.0",
    "Accept": "application/json, text/html, */*",
}


class FluidtopicsClient:
    """Stateful HTTP client for one Fluidtopics documentation map.

    Usage::

        with FluidtopicsClient(api_base="https://docs.example.com", map_id="abc") as client:
            pages = client.get_pages()
            html = client.get_content("topicId123")
    """

    def __init__(self, api_base: str, map_id: str, delay: float = 0.3) -> None:
        """
        Args:
            api_base: Root URL of the Fluidtopics instance, e.g. "https://docs.tia.siemens.cloud".
            map_id:   Fluidtopics map identifier — visible in the /api/khub/maps/{map_id}/ URLs.
            delay:    Seconds to sleep between requests (polite crawling). Default 0.3 s.
        """
        self._api_base = api_base.rstrip("/")
        self._map_id = map_id
        self._delay = delay
        self._http = httpx.Client(
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        self._session_established = False

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _ensure_session(self) -> None:
        """Establish an anonymous session cookie if not already done."""
        if self._session_established:
            return
        log.debug("Establishing Fluidtopics session…")
        resp = self._http.get(f"{self._api_base}/internal/api/webapp/authentication/session")
        resp.raise_for_status()
        self._session_established = True
        log.debug("Session established (cookies: %s)", dict(self._http.cookies))

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_pages(self) -> dict:
        """Return the complete TOC tree for the configured map.

        The response shape is::

            {
                "configuration": {"splitCurrentPageToc": bool},
                "paginatedToc": [
                    {
                        "tocId": str,
                        "contentId": str,
                        "title": str,
                        "prettyUrl": str,
                        "pageToc": [... child nodes with "children" key ...]
                    }
                ]
            }
        """
        self._ensure_session()
        url = f"{self._api_base}/api/khub/maps/{self._map_id}/pages"
        log.debug("GET %s", url)
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_content(self, content_id: str) -> str:
        """Return raw HTML content for a single topic.

        Args:
            content_id: The ``contentId`` value from a TOC node.

        Returns:
            Raw HTML string ready for Markdown conversion.
        """
        import time

        self._ensure_session()
        url = (
            f"{self._api_base}/api/khub/maps/{self._map_id}"
            f"/topics/{content_id}/content"
        )
        log.debug("GET %s", url)
        resp = self._http.get(url, params={"target": "DESIGNED_READER"})
        resp.raise_for_status()
        time.sleep(self._delay)
        return resp.text

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "FluidtopicsClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self._http.close()
