"""MCP tool logic: pure functions returning Markdown strings."""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from scraper.catalog import SW_VERSION_KEY, TIA_VERSION_KEY, Catalog

log = logging.getLogger(__name__)

MAX_LIMIT = 50
MAX_PUBLICATIONS = 50


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
    header = f'Found {data.get("totalResultsCount", len(topics))} results for "{query}" on {host}. Showing {len(topics)}:'
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
    maps = catalog.filter(host, product=product, version=version, locale=locale, title_contains=title_contains)
    if not maps:
        return f"No publications match these filters on {host}."
    rows = [
        f"- **{m.title}** — {m.product} {m.version} [{m.locale}] https://{host}/r/{m.pretty_url}"
        for m in maps[:MAX_PUBLICATIONS]
    ]
    if len(maps) > MAX_PUBLICATIONS:
        rows.append(f"Showing {MAX_PUBLICATIONS} of {len(maps)} — narrow your filters.")
    return "\n".join(rows)
