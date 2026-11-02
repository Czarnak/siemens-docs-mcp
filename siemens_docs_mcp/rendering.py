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
