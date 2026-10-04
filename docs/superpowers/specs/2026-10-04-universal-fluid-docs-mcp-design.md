# Universal Siemens Fluid Topics Docs — MCP Server Design

Date: 2026-10-04
Status: Approved (brainstorming), pending spec review

## 1. Goal

Turn this repo from a TIA-Openness-only batch scraper into an MCP server that lets an AI agent
search and read **any publication on any allowed Siemens Fluid Topics host**, live, without
hand-configuring a `map_id`. The existing CLI exporter stays and shares the same core.

**Success criteria**

- An agent can go from a natural-language question to the right page's Markdown in any of the
  ~4,000 publications on `docs.tia.siemens.cloud` (and on `docs.industrial-operations-x.siemens.cloud`)
  using only the MCP tools.
- Any reader URL an agent encounters (pretty URL or `/r/{mapId}/{contentId}`) can be passed to
  `read_page` / `get_toc` directly.
- The CLI can export a publication given only its reader URL.
- No DevTools step to find a `map_id`.

**Non-goals (YAGNI — add when a real need appears)**

- Offline mirror / local full-text index served by MCP.
- Disk cache.
- Login / restricted content.
- Non-Fluid-Topics Siemens sources (SIOS `support.industry.siemens.com`, `docs.sw.siemens.com`).
- MCP resources/prompts; HTTP transport (stdio only).

## 2. Verified facts (live, anonymous, 2026-10-04)

| Endpoint | Behaviour |
|---|---|
| `GET /internal/api/webapp/authentication/session` | Sets anonymous session cookie (200). |
| `GET /api/khub/maps` | Full catalog: 4,073 maps on TIA host (~16 MB JSON), 711 `en-US`. Each map: `id`, `title`, `metadata[]`. |
| `GET /api/khub/maps/{mapId}/pages` | TOC tree (already used). |
| `GET /api/khub/maps/{mapId}/topics/{contentId}/content?target=DESIGNED_READER` | Topic HTML (already used). |
| `POST /api/khub/clustered-search` | Full-text search. Body: `query`, `contentLocale`, `paging{perPage,page}`, `filters[{key,values}]`. Returns `results[].entries[].topic` with `mapId`, `contentId`, `title`, `mapTitle`, `breadcrumb`, `htmlExcerpt`, `readerUrl`, `metadata`. |
| `GET /api/khub/pretty-url/resolve` | Not available (404/405) — resolution must be done from the catalog. |

Useful map metadata keys: `ft:prettyUrl` (e.g. `en-us/v21/tia-portal-openness-api-for-automation-of-engineering-workflows`),
`ft:locale`, `Product` / `Product_custom`, `SoftwareVersion`, `tia:SoftwareVersionFilter` (e.g. `V21`),
`ft:clusterId`, `ft:lastPublication`.

Hosts answering the Fluid Topics API: `docs.tia.siemens.cloud`, `docs.industrial-operations-x.siemens.cloud`.

HTML observations:

- TIA publications (Openness, STEP 7, WinCC Unified) share authoring classes (`Blocktitle`,
  `p_table_l_code`, `table_sourcecode`, `safety`). Current converter handles them, but fences
  all source code as `csharp` — wrong for SCL etc.
- IOX publications use MkDocs-style HTML (`admonition`, `note`, `admonition-title`, `highlight`).
- In-page links are absolute reader URLs of the form `https://{host}/r/{mapId}/{contentId}`.

## 3. Architecture

One shared core package (`scraper/`, name kept to avoid churn); two front ends.

```
server.py (MCP, stdio) ─┐
                        ├─> scraper/catalog.py ─> scraper/client.py ─> Fluid Topics REST
main.py   (CLI export) ─┘   scraper/toc.py, content.py, converter.py, writer.py
```

| Module | Responsibility | Change |
|---|---|---|
| `scraper/client.py` | HTTP to one host. `list_maps()`, `get_pages(map_id)`, `get_content(map_id, content_id)`, `search(query, locale, filters, page, per_page)`. Session handling, throttle, retry. | Refactor: per-host instead of per-map. |
| `scraper/catalog.py` | Cached map list per host; URL resolution; publication filtering; TOC cache. | New. |
| `scraper/toc.py` | Parse `/pages` into `TocPage` tree. | Unchanged except as needed for subtree lookup by `content_id`. |
| `scraper/content.py` | Fetch + pre-clean HTML. | Take `map_id` per call. |
| `scraper/converter.py` | HTML → Markdown. | Generalize (see §6). |
| `scraper/writer.py` | Output paths. | Unchanged. |
| `server.py` | MCP server exposing 4 tools. | New. |
| `main.py` | CLI export. | Config accepts `url:`; resolves `map_id` via catalog. |

### 3.1 Client (`scraper/client.py`)

- One `httpx.Client` per host, created lazily and reused.
- **Throttle:** minimum interval between any two requests to the same host (default `0.3` s,
  env `SIEMENS_DOCS_MIN_INTERVAL`). Implemented with a `threading.Lock` + last-request
  monotonic timestamp, so concurrent tool calls queue rather than burst. Applies to every
  request (session, catalog, TOC, content, search). Replaces the current `time.sleep` in
  `get_content`.
- **Session:** establish lazily; on 401/403 re-establish once and retry the request once.
- **Retry:** on 429 or 5xx, retry once after `Retry-After` seconds if present (capped at 30 s),
  else a 2 s backoff. Second failure raises.
- Timeouts: 30 s default; 120 s for the catalog request.

### 3.2 Catalog (`scraper/catalog.py`)

- `Catalog(hosts: list[str], ttl_seconds=86400)` holding per-host `{map_id: MapInfo}`.
  `MapInfo` = `id, title, locale, product, version, pretty_url, cluster_id, last_publication`
  (product from `Product` — the key search filters on; version from
  `tia:SoftwareVersionFilter`, falling back to `SoftwareVersion` for maps without it, e.g. IOX).
- Loaded lazily per host on first use, refreshed when older than TTL. In-memory only.
- `resolve(url) -> (host, map_id, content_id | None)`:
  1. Parse URL; host must be in the allowlist, else error.
  2. `/r/{mapId}/{contentId}` or `/r/{mapId}` where `mapId` is a known map id → direct.
  3. Otherwise pretty URL `/r/{path}`: find the map whose `ft:prettyUrl` is the longest prefix
     of `path`. If `path` equals it → map root (content_id `None`). If longer → load that
     map's TOC (cached) and match the node whose `prettyUrl` equals `/r/{path}`.
  4. No match → error suggesting `search_docs` / `list_publications`.
- `canonical(host, key, value) -> str` — maps agent input to the exact catalog value
  (case-insensitive equality) for `product`, `version`, `locale`; unknown → error with close
  matches (see §4).
- `filter(host, product, version, locale, title_contains) -> list[MapInfo]` — exact match on
  canonicalized product/version/locale, case-insensitive substring on title.
- TOC cache: `get_toc(host, map_id) -> TocPage`, same TTL.

### 3.3 Configuration (server)

| Env var | Default | Meaning |
|---|---|---|
| `SIEMENS_DOCS_HOSTS` | — | Comma-separated extra hosts appended to the built-in allowlist. |
| `SIEMENS_DOCS_LOCALE` | `en-US` | Default content locale. |
| `SIEMENS_DOCS_MIN_INTERVAL` | `0.3` | Seconds between requests per host. |

Built-in allowlist: `docs.tia.siemens.cloud`, `docs.industrial-operations-x.siemens.cloud`.
Default host for tools that take `host`: first entry (`docs.tia.siemens.cloud`).
Hosts are bare hostnames; the server always uses `https://`.

## 4. MCP tools (`server.py`)

Built on the official MCP Python SDK v2 (`from mcp.server import MCPServer`, `@mcp.tool()`,
`mcp.run()` stdio). Pin `mcp>=2,<3`. Failures raise `ToolError` so the message reaches the agent
as an `is_error` result. All tools return Markdown text.

| Tool | Parameters | Returns |
|---|---|---|
| `search_docs` | `query: str`, `host: str = default`, `product: str \| None`, `version: str \| None`, `locale: str = default`, `limit: int = 10` (1–50) | Numbered list: title, publication title + version, breadcrumb, plain-text excerpt (HTML stripped), reader URL. Footer with total hit count. |
| `read_page` | `url: str`, `offset: int = 0`, `max_chars: int = 20000` | Header (publication, version, breadcrumb/title, source URL) + Markdown body slice. If more remains: `[truncated — call again with offset=N]`. Map-root URL reads the root topic. |
| `get_toc` | `url: str`, `depth: int = 2` (1–6) | Indented outline of the publication (or of the subtree under the topic in `url`), one line per node: title + reader URL. Capped at 500 lines with a "use a deeper URL or smaller depth" note. |
| `list_publications` | `host: str = default`, `product: str \| None`, `version: str \| None`, `locale: str = default`, `title_contains: str \| None` | Up to 50 rows: title, product, version, locale, reader URL. Footer with total and "narrow your filters" if capped. |

Search filters (verified live 2026-10-04): `product` → `{"key": "Product", "values": [v]}`,
`version` → `{"key": "tia:SoftwareVersionFilter", "values": [v]}`; both combine with AND.
The server matches filter values **exactly and case-sensitively** (`"step 7"` → 0 hits), so the
tool first canonicalizes the agent's input against the distinct values seen in that host's
catalog (case-insensitive equality, e.g. `step 7` → `STEP 7`, `v21` → `V21`). If no catalog value
matches, raise `ToolError` listing the closest known values (`difflib.get_close_matches`).
`list_publications` uses the same canonicalization.

Reader URL for a TOC node: `https://{host}{prettyUrl}` when present, else
`https://{host}/r/{mapId}/{contentId}`.

## 5. Data flow (typical agent session)

1. `search_docs("export PLC block", product="STEP 7", version="V21")` → hits with reader URLs.
2. `read_page(url)` → catalog resolves → client fetches content → `fetch_html` cleans →
   converter → header + body slice. Links in body are absolute reader URLs, re-usable as input.
3. `get_toc(url, depth=2)` → navigate around the hit.
4. `list_publications(product="WinCC Unified", version="V21")` → find a publication to browse.

## 6. Converter changes (`scraper/converter.py`)

- Source-code fences: drop hardcoded `csharp`; emit plain ```` ``` ```` fences. (No language
  guessing — a wrong tag is worse than none.)
- MkDocs admonitions (`div.admonition`, title from `.admonition-title`) → Markdown blockquote
  `> **Note:** …`, same shape as existing safety tables.
- Unknown block tags: fall back to `markdownify` (already a dependency) instead of plain text,
  so lists/tables/code inside unfamiliar wrappers survive.
- Keep existing TIA-specific handling (Blocktitle → H2, safety tables, code tables).
- Preserve absolute links as-is.

## 7. CLI changes (`main.py`)

- Config may give `url:` (a publication reader URL). `api_base` and `map_id` are derived via
  the catalog. Legacy `api_base` + `map_id` configs keep working.
- Uses the shared client (throttle replaces ad-hoc sleep). Behaviour otherwise unchanged:
  per-page failures are logged, the run continues, failures summarized at the end.
- README updated: drop the DevTools instructions, document `url:` and the MCP server setup.

## 8. Error handling

| Situation | Behaviour |
|---|---|
| Host not in allowlist | `ToolError` listing allowed hosts. |
| URL not resolvable | `ToolError` suggesting `search_docs` / `list_publications`. |
| 401/403 | Re-establish session, retry once; then `ToolError` with status. |
| 429 / 5xx | One retry honouring `Retry-After` (≤30 s) or 2 s; then `ToolError` with status. |
| Empty content | Header + `*No content available.*` |
| Invalid params (limit/depth out of range, offset < 0) | `ToolError` with the valid range. |
| Network error / timeout | `ToolError` with a short description; no stack trace to the agent. |

## 9. Testing

- Move `test_scraper.py` checks into `tests/` and run with `pytest` (dev dependency in
  `requirements-dev.txt`).
- **Offline unit tests** with trimmed real fixtures in `tests/fixtures/`: catalog slice
  (both hosts), one `/pages` TOC, one search response, HTML from TIA Openness, STEP 7/SCL and
  an IOX admonition page. HTTP mocked with `httpx.MockTransport` (no new dependency).
  Cover:
  - URL resolution: pretty map URL, pretty topic URL, `/r/{map}/{content}`, unknown host,
    unknown path.
  - Catalog filtering by product/version/locale/title.
  - Converter: SCL code without `csharp`, admonition → blockquote, existing regressions.
  - `read_page` truncation/offset footer; `get_toc` depth and line cap.
  - Throttle: two consecutive requests are spaced ≥ interval (inject a fake clock).
  - Retry: 429 with `Retry-After` retried once; 401 re-establishes session once.
  - Tool errors: messages for each row of §8.
- **Live smoke test** marked `@pytest.mark.live`, skipped by default: search → read → toc on
  both hosts.
- CI (`.github/workflows/ci.yml`): run `pytest -m "not live"`.

## 10. Risks

- **Unofficial API** — Siemens can change or restrict it. Mitigation: throttle, small surface,
  live smoke test to detect breakage.
- **Catalog size (~16 MB per host)** — first call per host takes a few seconds. Acceptable;
  cached for 24 h.
- **Metadata inconsistency** (`Product` vs `Product_custom`, `TIA Portal` vs `TIAPortal`) —
  canonicalization against catalog values with close-match suggestions; `MapInfo.product` is
  taken from `Product` (the key search filters on) so list and search agree.
- **Pretty-URL resolution for topics** requires loading that map's TOC — one extra request,
  cached.
