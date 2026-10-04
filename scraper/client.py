"""HTTP client for the Fluidtopics REST API (one client per host).

Fluidtopics requires a session cookie obtained from the authentication endpoint
before any /api/khub/ calls will succeed. This client acquires that cookie
automatically, throttles every request to the host, and retries once on
auth expiry, 429 and 5xx.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from typing import Self

import httpx

log = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    # Identify ourselves politely; some servers reject requests without UA.
    "User-Agent": "docs-scraper/1.0",
    "Accept": "application/json, text/html, */*",
}

_SESSION_PATH = "/internal/api/webapp/authentication/session"
_DEFAULT_TIMEOUT = 30.0
_MAPS_TIMEOUT = 120.0
_BACKOFF_DEFAULT = 2.0
_BACKOFF_MAX = 30.0


class FluidtopicsError(Exception):
    """Request to a Fluidtopics host failed; ``status`` is None for network errors."""

    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(message)
        self.status = status


def _backoff_seconds(resp: httpx.Response) -> float:
    """Seconds to wait before retrying: Retry-After (capped), else 2 s."""
    try:
        value = float(resp.headers.get("Retry-After", ""))
    except ValueError:
        return _BACKOFF_DEFAULT
    if not math.isfinite(value) or value < 0:
        return _BACKOFF_DEFAULT
    return min(value, _BACKOFF_MAX)


class FluidtopicsClient:
    """Stateful HTTP client for one Fluidtopics host.

    Usage::

        with FluidtopicsClient("docs.tia.siemens.cloud") as client:
            pages = client.get_pages("map-id")
            html = client.get_content("map-id", "topicId123")
    """

    def __init__(
        self,
        host: str,
        min_interval: float = 0.3,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._host = host
        self._base = f"https://{host}"
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last = -math.inf
        self._http = httpx.Client(
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=_DEFAULT_TIMEOUT,
            transport=transport,
        )
        self._session_established = False

    @property
    def host(self) -> str:
        return self._host

    # ------------------------------------------------------------------
    # Transport, session, retry
    # ------------------------------------------------------------------

    def _send(self, method: str, path: str, **kw: object) -> httpx.Response:
        """Throttled single request; transport failures become FluidtopicsError."""
        with self._lock:
            wait = self._last + self._min_interval - self._clock()
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()
        log.debug("%s %s%s", method, self._base, path)
        try:
            return self._http.request(method, f"{self._base}{path}", **kw)
        except httpx.TransportError as exc:
            raise FluidtopicsError(None, f"network error contacting {self._host}: {exc}") from exc

    def _ensure_session(self) -> None:
        if self._session_established:
            return
        resp = self._send("GET", _SESSION_PATH)
        if not resp.is_success:
            raise FluidtopicsError(resp.status_code, f"GET {_SESSION_PATH} -> HTTP {resp.status_code}")
        self._session_established = True

    def _request(self, method: str, path: str, **kw: object) -> httpx.Response:
        self._ensure_session()
        resp = self._send(method, path, **kw)
        if resp.status_code in (401, 403):
            self._session_established = False
            self._ensure_session()
            resp = self._send(method, path, **kw)
        elif resp.status_code == 429 or resp.status_code >= 500:
            self._sleep(_backoff_seconds(resp))
            resp = self._send(method, path, **kw)
        if not resp.is_success:
            raise FluidtopicsError(resp.status_code, f"{method} {path} -> HTTP {resp.status_code}")
        return resp

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def list_maps(self) -> list[dict]:
        """Return all maps (publications) hosted on this server."""
        return self._request("GET", "/api/khub/maps", timeout=_MAPS_TIMEOUT).json()

    def get_pages(self, map_id: str) -> dict:
        """Return the complete TOC tree (``paginatedToc``) for a map."""
        return self._request("GET", f"/api/khub/maps/{map_id}/pages").json()

    def get_content(self, map_id: str, content_id: str) -> str:
        """Return raw HTML content for a single topic."""
        resp = self._request(
            "GET",
            f"/api/khub/maps/{map_id}/topics/{content_id}/content",
            params={"target": "DESIGNED_READER"},
        )
        return resp.text

    def search(
        self,
        query: str,
        locale: str,
        filters: list[dict] | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> dict:
        """Run a clustered search; ``filters`` are sent only when non-empty."""
        body: dict = {
            "query": query,
            "contentLocale": locale,
            "paging": {"page": page, "perPage": per_page},
        }
        if filters:
            body["filters"] = filters
        return self._request("POST", "/api/khub/clustered-search", json=body).json()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self._http.close()
