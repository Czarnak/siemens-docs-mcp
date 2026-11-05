"""Pure Markdown rendering of prepared documentation results."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from siemens_docs_mcp.catalog import MapInfo


@dataclass(frozen=True)
class SearchHit:
    title: str
    map_title: str
    version: str
    breadcrumb: tuple[str, ...]
    excerpt: str
    reference: str


def render_search(query: str, host: str, total: int, hits: Sequence[SearchHit]) -> str:
    if not hits:
        return f'No results for "{query}" on {host}.'
    lines = [f'Found {total} results for "{query}" on {host}. Showing {len(hits)}:']
    for index, hit in enumerate(hits, 1):
        suffix = f" ({hit.version})" if hit.version else ""
        lines.append(
            f"{index}. **{hit.title}** — {hit.map_title}{suffix}\n"
            f"   {' > '.join(hit.breadcrumb)}\n"
            f"   {hit.excerpt}\n"
            f"   {hit.reference}"
        )
    return "\n".join(lines)


def render_scoped_search(
    query: str,
    publication: MapInfo,
    topic_title: str | None,
    total: int,
    hits: Sequence[SearchHit],
    scan: tuple[int, int | None] | None = None,
) -> str:
    """Hits within one publication or topic subtree.

    ``scan`` is ``(checked, publication_total)`` when a subtree scan stopped before checking every
    publication hit (the total is None when unknown); ``total`` is then only a lower bound and is not shown.
    """
    scope = f"{publication.title} ({publication.version})" if publication.version else publication.title
    if topic_title is not None:
        scope = f'"{topic_title}" — {scope}'
    checked = "" if scan is None else f"{scan[0]}" + ("" if scan[1] is None else f" of {scan[1]}")
    if not hits:
        if scan is None:
            return f'No results for "{query}" in {scope}.'
        return (
            f'No results for "{query}" in {scope} among the first {checked} publication results. '
            "Try a narrower query or search the whole publication."
        )
    if scan is None:
        header = f'Found {total} results for "{query}" in {scope}. Showing {len(hits)}:'
    else:
        header = (
            f'Showing {len(hits)} results for "{query}" in {scope}; '
            f"checked {checked} publication results, more may exist:"
        )
    # The header names the publication, so hits skip the per-hit "— publication (version)" suffix.
    lines = [header]
    for index, hit in enumerate(hits, 1):
        lines.append(
            f"{index}. **{hit.title}**\n"
            f"   {' > '.join(hit.breadcrumb)}\n"
            f"   {hit.excerpt}\n"
            f"   {hit.reference}"
        )
    return "\n".join(lines)


def render_publications(host: str, rows: Sequence[tuple[MapInfo, str]], total: int, limit: int) -> str:
    if not rows:
        return f"No publications match these filters on {host}."
    lines = [
        f"- **{info.title}** — {info.product} {info.version} [{info.locale}] {reference}"
        for info, reference in rows
    ]
    if total > limit:
        lines.append(f"Showing {limit} of {total} — narrow your filters.")
    return "\n".join(lines)


def render_page(publication: MapInfo, path: Sequence[str], source: str, chunk: str) -> str:
    header = (
        f"> Publication: {publication.title} ({publication.version}) [{publication.locale}]\n"
        f"> Path: {' > '.join(path)}\n"
        f"> Source: {source}"
    )
    return f"{header}\n\n{chunk}"


def render_toc(rows: Sequence[tuple[int, str, str]], truncated: bool, limit: int) -> str:
    lines = [f"{'  ' * level}- {title} — {reference}" for level, title, reference in rows]
    if truncated:
        lines.append(f"… truncated at {limit} lines — use a deeper reference or a smaller depth.")
    return "\n".join(lines)
