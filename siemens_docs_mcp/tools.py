"""MCP tool retrieval, normalization, and pagination returning Markdown strings."""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from siemens_docs_mcp.catalog import (
    SW_VERSION_KEY,
    TIA_VERSION_KEY,
    Catalog,
    CatalogError,
    ReferenceFormat,
    Resolved,
    validate_reference_format,
)
from siemens_docs_mcp.content import fetch_html
from siemens_docs_mcp.converter import html_to_markdown
from siemens_docs_mcp.rendering import (
    SearchHit,
    render_page,
    render_publications,
    render_search,
    render_toc,
)
from siemens_docs_mcp.toc import TocPage, find_path

log = logging.getLogger(__name__)

MAX_LIMIT = 50
MAX_PUBLICATIONS = 50
MIN_CHARS, MAX_CHARS = 1000, 100_000
MAX_DEPTH = 6
MAX_TOC_LINES = 500


def _search_reference(catalog: Catalog, host: str, topic: dict, reference_format: ReferenceFormat) -> str:
    map_id, content_id = topic.get("mapId"), topic.get("contentId")
    if isinstance(map_id, str) and isinstance(content_id, str):
        target = Resolved(host, map_id, content_id)
        try:
            compact = catalog.compact_ref(target)
        except CatalogError:
            pass  # Malformed upstream IDs may still carry a usable reader URL.
        else:
            if reference_format == "compact":
                return compact
            return catalog.fallback_reader_url(topic.get("readerUrl")) or catalog.id_url(target)
    return catalog.fallback_reader_url(topic.get("readerUrl")) or "(reference unavailable)"


def _normalize_hit(topic: dict, reference: str) -> SearchHit:
    meta = {m.get("key"): m.get("values") or [] for m in topic.get("metadata", [])}
    version = ""
    for key in (TIA_VERSION_KEY, SW_VERSION_KEY):
        if meta.get(key):
            version = meta[key][0]
            break
    # Highlight spans carry their own spacing; a get_text separator would split "on-delay" into "on - delay".
    excerpt = " ".join(BeautifulSoup(topic.get("htmlExcerpt") or "", "html.parser").get_text().split())
    return SearchHit(
        title=topic.get("title", ""),
        map_title=topic.get("mapTitle", ""),
        version=version,
        breadcrumb=tuple(topic.get("breadcrumb") or []),
        excerpt=excerpt,
        reference=reference,
    )


def search_docs(
    catalog: Catalog,
    query: str,
    host: str,
    locale: str,
    product: str | None = None,
    version: str | None = None,
    limit: int = 10,
    *,
    reference_format: ReferenceFormat = "compact",
) -> str:
    """Full-text search on one host; returns a Markdown list of hits."""
    validate_reference_format(reference_format)
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
        return render_search(query, host, 0, [])
    total = data.get("paging", {}).get("totalResultsCount", len(topics))
    hits = [_normalize_hit(topic, _search_reference(catalog, host, topic, reference_format)) for topic in topics]
    return render_search(query, host, total, hits)


def list_publications(
    catalog: Catalog,
    host: str,
    locale: str,
    product: str | None = None,
    version: str | None = None,
    title_contains: str | None = None,
    *,
    reference_format: ReferenceFormat = "compact",
) -> str:
    """List publications on one host matching the filters (capped at 50 rows)."""
    validate_reference_format(reference_format)
    locale = catalog.canonical(host, "locale", locale)
    # LLM clients send "" for unset optional params; treat it as "no filter" like search_docs does.
    maps = catalog.filter(
        host, product=product or None, version=version or None, locale=locale, title_contains=title_contains or None
    )
    rows = [
        (m, catalog.compact_ref(Resolved(host, m.id, None)) if reference_format == "compact" else catalog.map_url(host, m.id))
        for m in maps[:MAX_PUBLICATIONS]
    ]
    return render_publications(host, rows, len(maps), MAX_PUBLICATIONS)


def read_page(
    catalog: Catalog, url: str, offset: int = 0, max_chars: int = 20000,
    *, reference_format: ReferenceFormat = "compact",
) -> str:
    """Read one topic as Markdown with a provenance header; page through it with ``offset``."""
    validate_reference_format(reference_format)
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
        content_id = path[-1].content_id  # the link may have named the tocId
        title = path[-1].title
        source = (
            catalog.compact_ref(Resolved(res.host, res.map_id, content_id))
            if reference_format == "compact" else catalog.reader_url(res.host, res.map_id, path[-1])
        )
        titles = [p.title or info.title for p in path]
    else:
        title = "(untitled topic)"
        target = Resolved(res.host, res.map_id, content_id)
        source = catalog.compact_ref(target) if reference_format == "compact" else catalog.id_url(target)
        titles = [info.title]
    html = fetch_html(catalog.client(res.host), res.map_id, content_id)
    body = html_to_markdown(html, title)
    if offset >= len(body) > 0:
        raise ValueError(f"offset {offset} is past the end of this page (length {len(body)}).")
    end = offset + max_chars
    chunk = body[offset:end]
    if end < len(body):
        chunk += f"\n\n[truncated — call again with offset={end}]"
    return render_page(info, titles, source, chunk)


def get_toc(catalog: Catalog, url: str, depth: int = 2, *, reference_format: ReferenceFormat = "compact") -> str:
    """Indented TOC outline of a publication or of the subtree under a topic reference."""
    validate_reference_format(reference_format)
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
                f"Topic {res.content_id} is not in this publication's TOC. Use search_docs to find a valid reference."
            )
        start = path[-1]
    rows: list[tuple[int, str, str]] = []

    def walk(node: TocPage, level: int) -> None:
        reference = (
            catalog.compact_ref(Resolved(res.host, res.map_id, node.content_id or None))
            if reference_format == "compact" else catalog.reader_url(res.host, res.map_id, node)
        )
        rows.append((level, node.title or pub_title, reference))
        if level < depth:
            for child in node.children:
                walk(child, level + 1)

    walk(start, 0)
    return render_toc(rows[:MAX_TOC_LINES], len(rows) > MAX_TOC_LINES, MAX_TOC_LINES)
