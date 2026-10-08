"""Parse the Fluidtopics /pages API response into a typed tree of TocPage objects.

The raw API response uses two different keys depending on nesting depth:
- The root node stores its children under ``"pageToc"``
- All descendant nodes store their children under ``"children"``

Both are handled transparently by ``_parse_node``.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


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

    children: list[TocPage] = field(default_factory=list)

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
    if len(paginated) > 1:
        # No root topic: each top-level section is its own entry. Add an empty-id root
        # (pretty_url = the sections' common parent) so every section keeps a parent.
        first = paginated[0]["prettyUrl"]
        root = TocPage("", "", "", first.rsplit("/", 1)[0], 0)
        root.children = [_parse_node(n, depth=1, parent=root) for n in paginated]
        return root
    return _parse_node(paginated[0], depth=0)


def iter_pages(root: TocPage) -> Iterator[TocPage]:
    """Yield every page in the tree in depth-first (pre-order) order."""
    yield root
    for child in root.children:
        yield from iter_pages(child)


def find_path(root: TocPage, content_id: str) -> list[TocPage] | None:
    """Return the root-to-node path for ``content_id`` (DFS), or None if absent.

    Also matches ``toc_id``: in-page links point at ``/r/{map}/{tocId}``.
    """
    if content_id in (root.content_id, root.toc_id):
        return [root]
    for child in root.children:
        sub = find_path(child, content_id)
        if sub is not None:
            return [root, *sub]
    return None


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
