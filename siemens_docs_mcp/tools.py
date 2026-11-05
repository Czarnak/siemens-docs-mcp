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
from siemens_docs_mcp.client import FluidtopicsClient, FluidtopicsError
from siemens_docs_mcp.content import fetch_soup
from siemens_docs_mcp.converter import Block, LinkRewrite, html_to_blocks
from siemens_docs_mcp.reading import (
    READ_MODES,
    ReadMode,
    chunk_view,
    code_view,
    outline_rows,
    select_sections,
    view_text,
)
from siemens_docs_mcp.rendering import (
    SearchHit,
    render_continuation,
    render_outline,
    render_page,
    render_publications,
    render_scoped_search,
    render_search,
    render_toc,
)
from siemens_docs_mcp.toc import TocPage, find_path, iter_pages

log = logging.getLogger(__name__)

MAX_LIMIT = 50
MAX_PUBLICATIONS = 50
MIN_CHARS, MAX_CHARS = 1000, 100_000
MAX_DEPTH = 6
MAX_TOC_LINES = 500
# Scoped search: the upstream metadata key holding a hit's map id (verified live on both hosts, 2026-11-05).
PUBLICATION_FILTER_KEY = "ft:publicationId"
# Subtree scope filters publication hits locally: read at most this many pages of this size.
SCOPE_PAGE_SIZE = 100
MAX_SCOPE_PAGES = 3


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


def _body_link(catalog: Catalog, reference_format: ReferenceFormat, host: str) -> LinkRewrite:
    """Page-body link policy: drop attachment URLs; topic links on the page's own host follow reference_format.

    Links to other hosts stay unchanged: whether their publication list is loaded depends on earlier calls,
    and the same page must always render the same text, or offsets from a previous call would drift.
    """
    def rewrite(href: str) -> str | None:
        if catalog.is_attachment_link(href):
            return None
        if reference_format == "compact":
            return catalog.compact_link(href, host=host) or href
        return href

    return rewrite


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


def _topic_path(catalog: Catalog, res: Resolved) -> list[TocPage]:
    """Root-to-topic TOC path for a topic reference (contentId or tocId)."""
    path = find_path(catalog.toc(res.host, res.map_id), res.content_id or "")
    if path is None:
        raise CatalogError(
            f"Topic {res.content_id} is not in this publication's TOC. Use search_docs to find a valid reference."
        )
    return path


def _scoped_total(paging: dict) -> int | None:
    """Hit count of a publication-scoped search, or None when the API reports none.

    Each cluster yields one scoped hit, so the cluster count is preferred over the result count.
    """
    for key in ("totalClustersCount", "totalResultsCount"):
        value = paging.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _scoped_topics(data: dict, target: Resolved) -> list[dict]:
    """One topic per cluster, taken from the scoped publication.

    The API silently ignores filters it does not understand, so a cluster whose topics name only
    other publications means the scope was not applied: fail rather than return out-of-scope hits.
    Topics without a map id cannot be placed in the scope and are skipped.
    """
    topics = []
    for cluster in data.get("results") or []:
        candidates = [e["topic"] for e in cluster.get("entries", []) if e.get("type") == "TOPIC" and e.get("topic")]
        topic = next((t for t in candidates if t.get("mapId") == target.map_id), None)
        if topic is not None:
            topics.append(topic)
            continue
        foreign = next((t["mapId"] for t in candidates if t.get("mapId") is not None), None)
        if foreign is not None:
            raise FluidtopicsError(
                None,
                f"{target.host} did not apply the publication filter (returned a hit from publication "
                f"{foreign!r}); refusing to return results outside the scope.",
            )
    return topics


def _scan_subtree(
    client: FluidtopicsClient, query: str, locale: str, target: Resolved, node: TocPage, limit: int,
) -> tuple[list[dict], int, tuple[int, int | None] | None]:
    """Publication-scoped pages filtered to ``node``'s subtree: (topics, matches, scan).

    ``scan`` is None when every publication hit was checked, so ``matches`` is exact; otherwise it is
    ``(checked, publication_total)``, with the total None when the API did not report one.
    """
    inside = {page.content_id for page in iter_pages(node)}
    filters = [{"key": PUBLICATION_FILTER_KEY, "values": [target.map_id]}]
    kept: list[dict] = []
    checked = 0
    publication_total: int | None = None
    for page in range(1, MAX_SCOPE_PAGES + 1):
        data = client.search(query, locale, filters, page=page, per_page=SCOPE_PAGE_SIZE)
        results = data.get("results") or []
        paging = data.get("paging") or {}
        checked += len(results)
        publication_total = _scoped_total(paging)
        kept += [t for t in _scoped_topics(data, target) if t.get("contentId") in inside]
        # Exact only on evidence: the last-page flag, a reached total, or an empty page with no total.
        if (
            paging.get("isLastPage")
            or (publication_total is not None and checked >= publication_total)
            or (not results and publication_total is None)
        ):
            return kept[:limit], len(kept), None
        if not results or len(kept) >= limit:
            break
    return kept[:limit], len(kept), (checked, publication_total)


def _scoped_search(
    catalog: Catalog,
    query: str,
    scope: str,
    host: str | None,
    locale: str | None,
    product: str | None,
    version: str | None,
    limit: int,
    reference_format: ReferenceFormat,
) -> str:
    if product or version:
        raise ValueError("scope already selects one publication; omit product and version.")
    target = catalog.resolve(scope)
    if host and host.lower() != target.host:
        raise ValueError(
            f"host {host!r} does not match scope {scope!r}, which is on {target.host}; omit host or make them match."
        )
    info = catalog.maps(target.host)[target.map_id]
    if locale and info.locale and locale.lower() != info.locale.lower():
        raise ValueError(
            f"locale {locale!r} does not match the scoped publication's locale {info.locale!r}; omit locale."
        )
    if not info.locale and not locale:
        raise ValueError("The scoped publication has no locale metadata; pass locale.")
    locale = info.locale or catalog.canonical(target.host, "locale", locale or "")
    node = None
    if target.content_id is not None:
        path = _topic_path(catalog, target)
        if len(path) > 1:  # the root topic stands for the whole publication
            node = path[-1]
    client = catalog.client(target.host)
    scan = None
    if node is None:
        filters = [{"key": PUBLICATION_FILTER_KEY, "values": [target.map_id]}]
        data = client.search(query, locale, filters, page=1, per_page=limit)
        topics = _scoped_topics(data, target)
        total = _scoped_total(data.get("paging") or {})
        total = len(topics) if total is None else total
    else:
        topics, total, scan = _scan_subtree(client, query, locale, target, node, limit)
    hits = [_normalize_hit(t, _search_reference(catalog, target.host, t, reference_format)) for t in topics]
    return render_scoped_search(query, info, node.title if node else None, total, hits, scan)


def search_docs(
    catalog: Catalog,
    query: str,
    host: str | None,
    locale: str | None,
    product: str | None = None,
    version: str | None = None,
    limit: int = 10,
    *,
    reference_format: ReferenceFormat = "compact",
    scope: str | None = None,
) -> str:
    """Full-text search on one host, or within a publication/topic ``scope``; returns a Markdown list of hits."""
    validate_reference_format(reference_format)
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be 1-{MAX_LIMIT}, got {limit}")
    if scope:
        return _scoped_search(catalog, query, scope, host, locale, product, version, limit, reference_format)
    if not host or not locale:
        raise ValueError("host and locale are required when no scope is given.")
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


def _reading_args(
    offset: int, max_chars: int, section: int | str | None, mode: str | None
) -> tuple[int | str | None, ReadMode]:
    """Validate read_page arguments before any request; returns (section, mode) normalized."""
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if not MIN_CHARS <= max_chars <= MAX_CHARS:
        raise ValueError(f"max_chars must be {MIN_CHARS}-{MAX_CHARS}, got {max_chars}")
    mode = mode or "full"  # LLM clients send "" for unset optional params
    if mode not in READ_MODES:
        raise ValueError(f"mode must be one of: {', '.join(READ_MODES)}; got {mode!r}")
    if isinstance(section, str):
        section = section.strip()
        section = int(section) if section.isdigit() else (section or None)
    if isinstance(section, bool) or (isinstance(section, int) and section < 0):
        raise ValueError(f"section must be an outline number (0 or more) or heading text, got {section!r}")
    if mode == "outline" and (section is not None or offset > 0):
        raise ValueError("mode='outline' takes neither section nor offset; it lists the whole page.")
    return section, mode


def read_page(
    catalog: Catalog, url: str, offset: int = 0, max_chars: int = 20000,
    *, reference_format: ReferenceFormat = "compact", section: int | str | None = None, mode: ReadMode = "full",
) -> str:
    """Read one topic as Markdown with a provenance header: the whole page, an outline, sections or code only.

    Long views are returned in chunks cut between blocks; the continuation line gives the exact arguments
    for the next chunk.
    """
    validate_reference_format(reference_format)
    section, mode = _reading_args(offset, max_chars, section, mode)
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
    soup = fetch_soup(catalog.client(res.host), res.map_id, content_id)
    body = html_to_blocks(soup, link=_body_link(catalog, reference_format, res.host), images=False) if soup else []
    full = [Block("heading", f"# {title}", 1), *(body or [Block("paragraph", "*No content available.*")])]
    if mode == "outline":
        return render_page(info, titles, source, render_outline(len(view_text(full)), outline_rows(body)))
    view = full if section is None else select_sections(body, section)
    if mode == "code":
        view = code_view(body if section is None else view)
        if not view:
            note = "No code blocks on this page." if section is None else "No code blocks in the selected sections."
            return render_page(info, titles, source, note)
    chunk = chunk_view(view, offset, max_chars)
    text = chunk.text
    if chunk.next_offset is not None:
        text += "\n\n" + render_continuation(chunk.next_offset, section, mode, reference_format)
    return render_page(info, titles, source, text)


def get_toc(catalog: Catalog, url: str, depth: int = 2, *, reference_format: ReferenceFormat = "compact") -> str:
    """Indented TOC outline of a publication or of the subtree under a topic reference."""
    validate_reference_format(reference_format)
    if not 1 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth must be 1-{MAX_DEPTH}, got {depth}")
    res = catalog.resolve(url)
    root = catalog.toc(res.host, res.map_id)
    pub_title = catalog.maps(res.host)[res.map_id].title
    start = root if res.content_id is None else _topic_path(catalog, res)[-1]
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
