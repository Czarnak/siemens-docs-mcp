"""MCP tool logic: pure functions returning Markdown strings."""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from scraper.catalog import SW_VERSION_KEY, TIA_VERSION_KEY, Catalog, CatalogError
from scraper.content import fetch_html
from scraper.converter import html_to_markdown
from scraper.toc import TocPage, find_path

log = logging.getLogger(__name__)

MAX_LIMIT = 50
MAX_PUBLICATIONS = 50
MIN_CHARS, MAX_CHARS = 1000, 100_000
MAX_DEPTH = 6
MAX_TOC_LINES = 500


def _hit_version(topic: dict) -> str:
    meta = {m.get("key"): m.get("values") or [] for m in topic.get("metadata", [])}
    for key in (TIA_VERSION_KEY, SW_VERSION_KEY):
        if meta.get(key):
            return meta[key][0]
    return ""


def _format_hit(index: int, topic: dict) -> str:
    version = _hit_version(topic)
    suffix = f" ({version})" if version else ""
    excerpt = BeautifulSoup(topic.get("htmlExcerpt") or "", "html.parser").get_text(" ", strip=True)
    return (
        f"{index}. **{topic.get('title', '')}** — {topic.get('mapTitle', '')}{suffix}\n"
        f"   {' > '.join(topic.get('breadcrumb') or [])}\n"
        f"   {excerpt}\n"
        f"   {topic.get('readerUrl', '')}"
    )


def search_docs(
    catalog: Catalog,
    query: str,
    host: str,
    locale: str,
    product: str | None = None,
    version: str | None = None,
    limit: int = 10,
) -> str:
    """Full-text search on one host; returns a Markdown list of hits."""
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be 1-{MAX_LIMIT}, got {limit}")
    client = catalog.client(host)
    locale = catalog.canonical(host, "locale", locale)
    filters: list[dict] = []
    if product:
        filters.append({"key": "Product", "values": [catalog.canonical(host, "product", product)]})
    if version:
        key, value = catalog.canonical_version(host, version)
        filters.append({"key": key, "values": [value]})
    data = client.search(query, locale, filters or None, page=1, per_page=limit)
    topics = []
    for cluster in data.get("results", []):
        topic = next((e["topic"] for e in cluster.get("entries", []) if e.get("type") == "TOPIC" and e.get("topic")), None)
        if topic:
            topics.append(topic)
    if not topics:
        return f'No results for "{query}" on {host}.'
    total = data.get("paging", {}).get("totalResultsCount", len(topics))
    header = f'Found {total} results for "{query}" on {host}. Showing {len(topics)}:'
    return "\n".join([header, *(_format_hit(i, t) for i, t in enumerate(topics, 1))])


def list_publications(
    catalog: Catalog,
    host: str,
    locale: str,
    product: str | None = None,
    version: str | None = None,
    title_contains: str | None = None,
) -> str:
    """List publications on one host matching the filters (capped at 50 rows)."""
    locale = catalog.canonical(host, "locale", locale)
    # LLM clients send "" for unset optional params; treat it as "no filter" like search_docs does.
    maps = catalog.filter(
        host, product=product or None, version=version or None, locale=locale, title_contains=title_contains or None
    )
    if not maps:
        return f"No publications match these filters on {host}."
    rows = [
        f"- **{m.title}** — {m.product} {m.version} [{m.locale}] {catalog.map_url(host, m.id)}"
        for m in maps[:MAX_PUBLICATIONS]
    ]
    if len(maps) > MAX_PUBLICATIONS:
        rows.append(f"Showing {MAX_PUBLICATIONS} of {len(maps)} — narrow your filters.")
    return "\n".join(rows)


def read_page(catalog: Catalog, url: str, offset: int = 0, max_chars: int = 20000) -> str:
    """Read one topic as Markdown with a provenance header; page through it with ``offset``."""
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if not MIN_CHARS <= max_chars <= MAX_CHARS:
        raise ValueError(f"max_chars must be {MIN_CHARS}-{MAX_CHARS}, got {max_chars}")
    res = catalog.resolve(url)
    try:
        info = catalog.maps(res.host)[res.map_id]
    except KeyError:
        raise CatalogError(f"Publication {res.map_id} not found on {res.host}.") from None
    root = catalog.toc(res.host, res.map_id)
    content_id = res.content_id or root.content_id or root.children[0].content_id
    path = find_path(root, content_id)
    if path:
        title, source = path[-1].title, catalog.reader_url(res.host, res.map_id, path[-1])
        titles = [p.title or info.title for p in path]
    else:
        title, source = "(untitled topic)", f"https://{res.host}/r/{res.map_id}/{content_id}"
        titles = [info.title]
    html = fetch_html(catalog.client(res.host), res.map_id, content_id)
    body = html_to_markdown(html, title)
    if offset >= len(body) > 0:
        raise ValueError(f"offset {offset} is past the end of this page (length {len(body)}).")
    end = offset + max_chars
    chunk = body[offset:end]
    if end < len(body):
        chunk += f"\n\n[truncated — call again with offset={end}]"
    header = (
        f"> Publication: {info.title} ({info.version}) [{info.locale}]\n"
        f"> Path: {' > '.join(titles)}\n"
        f"> Source: {source}"
    )
    return f"{header}\n\n{chunk}"


def get_toc(catalog: Catalog, url: str, depth: int = 2) -> str:
    """Indented TOC outline of a publication or of the subtree under a topic URL."""
    if not 1 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth must be 1-{MAX_DEPTH}, got {depth}")
    res = catalog.resolve(url)
    root = catalog.toc(res.host, res.map_id)
    pub_title = catalog.maps(res.host)[res.map_id].title
    start = root
    if res.content_id is not None:
        path = find_path(root, res.content_id)
        if path is None:
            raise CatalogError(
                f"Topic {res.content_id} is not in this publication's TOC. Use search_docs to find a valid URL."
            )
        start = path[-1]
    lines: list[str] = []

    def walk(node: TocPage, level: int) -> None:
        lines.append(f"{'  ' * level}- {node.title or pub_title} — {catalog.reader_url(res.host, res.map_id, node)}")
        if level < depth:
            for child in node.children:
                walk(child, level + 1)

    walk(start, 0)
    if len(lines) > MAX_TOC_LINES:
        lines = [*lines[:MAX_TOC_LINES], f"… truncated at {MAX_TOC_LINES} lines — use a deeper URL or a smaller depth."]
    return "\n".join(lines)
