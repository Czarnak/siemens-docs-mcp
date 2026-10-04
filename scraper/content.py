"""Fetch and lightly pre-clean HTML content for a single documentation page.

The cleaning step removes navigation chrome (breadcrumbs, prev/next links,
feedback widgets) that Fluidtopics injects around the actual topic content.
markdownify then handles the HTML → Markdown conversion in a separate step.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Tag

from .client import FluidtopicsClient
from .toc import TocPage

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


def fetch_html(client: FluidtopicsClient, page: TocPage) -> str:
    """Fetch and pre-clean the HTML content for a page.

    Args:
        client: An active :class:`FluidtopicsClient`.
        page:   The TOC page to fetch content for.

    Returns:
        Cleaned HTML string, ready for Markdown conversion.
    """
    raw = client.get_content(page.content_id)
    if not raw or not raw.strip():
        log.warning("Empty content returned for '%s' (%s)", page.title, page.content_id)
        return ""
    return _clean_html(raw)


def _clean_html(html: str) -> str:
    """Remove navigation chrome from raw HTML."""
    soup = BeautifulSoup(html, "html.parser")

    for selector in _CHROME_SELECTORS:
        for el in soup.select(selector):
            # Type guard: BeautifulSoup's select() can return NavigableString
            if isinstance(el, Tag):
                el.decompose()

    return str(soup)
