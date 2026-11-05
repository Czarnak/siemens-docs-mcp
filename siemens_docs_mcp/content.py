"""Fetch and lightly pre-clean HTML content for a single documentation page.

The cleaning step removes navigation chrome (breadcrumbs, prev/next links,
feedback widgets) that Fluidtopics injects around the actual topic content.
The cleaned tree is handed to the converter as is, so each page is parsed once.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag

from .client import FluidtopicsClient

log = logging.getLogger(__name__)

# CSS selectors for elements that are navigation/UI chrome, not documentation.
# These are stripped before Markdown conversion.
_CHROME_SELECTORS = [
    "nav",
    "[role='navigation']",
    "[class*='breadcrumb']",
    "[class*='feedback']",
    "[class*='rating']",
    "[class*='prev-next']",
    "[class*='pagination']",
    "button",
    # Fluidtopics-specific UI elements
    "ft-reader-history-back-action",
    "ft-reader-action",
    "ft-slotted-floating-menu",
]


def fetch_soup(client: FluidtopicsClient, map_id: str, content_id: str) -> BeautifulSoup | None:
    """Fetch a page, parse it once and remove navigation chrome in place.

    Returns None when the API returns no content, so callers can show their empty-page text.
    """
    raw = client.get_content(map_id, content_id)
    if not raw or not raw.strip():
        log.warning("Empty content returned for %s", content_id)
        return None
    soup = BeautifulSoup(raw, "html.parser")
    _clean_soup(soup)
    return soup


def fetch_html(client: FluidtopicsClient, map_id: str, content_id: str) -> str:
    """Fetch and pre-clean the HTML content for a page, as a string ("" when empty)."""
    soup = fetch_soup(client, map_id, content_id)
    return "" if soup is None else str(soup)


def _clean_soup(soup: BeautifulSoup) -> None:
    """Remove navigation chrome from a parsed page, in place."""
    for selector in _CHROME_SELECTORS:
        for el in soup.select(selector):
            # Type guard: BeautifulSoup's select() can return NavigableString
            if isinstance(el, Tag):
                el.decompose()


def _clean_html(html: str) -> str:
    """Remove navigation chrome from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")
    _clean_soup(soup)
    return str(soup)
