"""Parse the Fluidtopics /pages API response into a typed tree of TocPage objects.

The raw API response uses two different keys depending on nesting depth:
- The root node stores its children under ``"pageToc"``
- All descendant nodes store their children under ``"children"``

Both are handled transparently by ``_parse_node``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TocPage:
    """Represents one page (topic) in the documentation TOC."""

    toc_id: str
    """Fluidtopics internal TOC identifier."""

    content_id: str
    """Topic content identifier — used to fetch HTML via the API."""

    title: str
    """Human-readable page title."""

    pretty_url: str
    """Full site-relative URL path, e.g. ``/r/en-us/v21/doc-name/chapter/page``."""

    depth: int
    """Nesting depth. 0 = root document, 1 = top-level chapter, etc."""

    children: list["TocPage"] = field(default_factory=list)

    segments: tuple[str, ...] = ()
    """URL path segments relative to the root page, one per TOC level.

    Derived from the parent's prettyUrl, so a title slash (``export/import``)
    stays a single segment instead of becoming an extra directory level.
    """


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def parse_toc(pages_response: dict) -> TocPage:
    """Parse the ``/api/khub/maps/{id}/pages`` response into a ``TocPage`` tree.

    Raises:
        ValueError: If the response does not contain a ``paginatedToc`` list.
    """
    paginated = pages_response.get("paginatedToc", [])
    if not paginated:
        raise ValueError(
            "Unexpected /pages response — 'paginatedToc' is missing or empty.\n"
            f"Keys present: {list(pages_response.keys())}"
        )
    root_raw = paginated[0]
    return _parse_node(root_raw, depth=0)


def iter_pages(root: TocPage) -> Iterator[TocPage]:
    """Yield every page in the tree in depth-first (pre-order) order."""
    yield root
    for child in root.children:
        yield from iter_pages(child)


def count_pages(root: TocPage) -> int:
    """Count the total number of pages in the tree."""
    return sum(1 for _ in iter_pages(root))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_node(node: dict, depth: int, parent: TocPage | None = None) -> TocPage:
    url: str = node["prettyUrl"]
    segments: tuple[str, ...] = ()
    if parent is not None:
        prefix = parent.pretty_url + "/"
        rel = url[len(prefix):] if url.startswith(prefix) else url.rsplit("/", 1)[-1]
        segments = (*parent.segments, rel)

    page = TocPage(
        toc_id=node["tocId"],
        content_id=node["contentId"],
        title=node["title"],
        pretty_url=url,
        depth=depth,
        segments=segments,
    )
    # Root-level nodes use "pageToc" for their children.
    # All other nodes use "children".
    children_raw: list[dict] = node.get("pageToc") or node.get("children") or []
    page.children = [_parse_node(child, depth + 1, page) for child in children_raw]
    return page
