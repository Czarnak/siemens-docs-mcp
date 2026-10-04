# Universal Fluid Topics Docs MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a stdio MCP server that searches and reads any publication on allowed Siemens Fluid Topics hosts live, and make the existing CLI exporter work from a plain reader URL.

**Architecture:** A per-host HTTP client (throttle, session, retry) feeds an in-memory `Catalog` (map list, URL resolution, filter canonicalization, TOC cache). Pure tool functions in `scraper/tools.py` turn catalog + client output into Markdown strings; `server.py` registers them with the MCP SDK and maps errors to `ToolError`. `main.py` (CLI) uses the same client and catalog.

**Tech Stack:** Python 3.12, httpx, BeautifulSoup4, markdownify, PyYAML, MCP Python SDK v2 (`mcp>=2.3.0,<3`, `from mcp.server import MCPServer`), pytest + anyio plugin, ruff, pip-audit; packaging via `pyproject.toml` (setuptools).

**Spec:** `docs/superpowers/specs/2026-10-04-universal-fluid-docs-mcp-design.md`

## Global Constraints

- Built-in host allowlist: `docs.tia.siemens.cloud`, `docs.industrial-operations-x.siemens.cloud`; first entry is the default host. Always `https://{host}`.
- Env vars: `SIEMENS_DOCS_HOSTS` (comma-separated extra hosts, appended), `SIEMENS_DOCS_LOCALE` (default `en-US`), `SIEMENS_DOCS_MIN_INTERVAL` (default `0.3`).
- Throttle: ≥ `min_interval` seconds between any two requests to the same host, every request type, thread-safe (lock held while waiting).
- Retry: 401/403 → re-establish session once, retry once. 429/5xx → retry once after `Retry-After` (capped 30 s) else 2 s.
- Timeouts: 30 s default, 120 s for `/api/khub/maps`.
- Cache: in-memory only, TTL 86400 s, nothing persisted.
- Tool limits: `search_docs.limit` 1–50 (default 10); `read_page.max_chars` 1000–100000 (default 20000), `offset` ≥ 0; `get_toc.depth` 1–6 (default 2), output capped at 500 lines; `list_publications` capped at 50 rows.
- Search filters: product → key `Product`; version → key `tia:SoftwareVersionFilter` or `SoftwareVersion` (whichever the canonical value came from). Values are matched exactly server-side, so always canonicalize first.
- Code fences from the converter carry no language tag.
- Tool failures surface as `mcp.server.mcpserver.exceptions.ToolError` with a human-readable message; no stack traces to the agent.
- Dependencies live only in `pyproject.toml` (no `requirements*.txt`). No new runtime dependency other than `mcp`. Dev tools in PEP 735 `[dependency-groups] dev` = `pytest`, `ruff`, `pip-audit`. Install: `python -m pip install -e . --group dev` (requires pip ≥ 25.1; venv has 26.2.1).
- **Newest versions policy:** every dependency floor is the latest release at the time it is added (checked with `python -m pip index versions <pkg>`). As of 2026-10-04: httpx 0.28.1, beautifulsoup4 4.15.0, markdownify 1.2.3, PyYAML 6.0.3, lxml 6.1.3, mcp 2.3.0, pytest 9.1.1, ruff 0.16.10, pip-audit 2.10.1, setuptools 84.0.0. Upper bounds only for known major-version breaks (`mcp<3`).
- Any task that changes dependencies runs `python -m pip_audit --skip-editable` and must end with no known vulnerabilities.
- Use the project venv: `.venv/Scripts/python.exe` (Windows). Commands below write `python` for brevity.

## Review Focus

1. **URL noise** — reader URLs with `?query`, `#fragment`, trailing `/`, `http://`, or upper-case host must resolve exactly like the clean URL. Pinned in Task 4 (`test_resolve_tolerates_url_noise`).
2. **IOX version filter** — IOX maps carry versions only in `SoftwareVersion` (`6.1`, `v26.01`); filtering with the TIA key would silently return 0 hits. Pinned in Task 4 (`test_canonical_version_uses_source_key`) and Task 5 (`test_search_docs_version_filter_key_for_iox`).
3. **Locale case** — pretty URLs use `en-us`, metadata uses `en-US`; agent input may be either. Pinned in Task 4 (`test_canonical_locale_case_insensitive`).
4. **Empty results / offset past end** — zero search hits or zero matching publications must say so explicitly; `offset` beyond the page length must error with the page length, not return an empty body. Pinned in Task 5 (`test_search_docs_no_results`, `test_list_publications_none`) and Task 6 (`test_read_page_offset_past_end`).
5. **Content-less unknown tags** — an unknown wrapper tag containing only text/inline nodes (e.g. `<pre>`, `<dl>`, `<span>` at block level) is currently dropped entirely by `_render_block`. Pinned in Task 2 (`test_unknown_inline_only_tag_not_dropped`).

---

## File Structure

| File | Responsibility |
|---|---|
| `scraper/client.py` (rewrite) | `FluidtopicsClient` per host; `FluidtopicsError`. |
| `scraper/catalog.py` (new) | `MapInfo`, `Resolved`, `CatalogError`, `Catalog`. |
| `scraper/toc.py` (modify) | add `find_path`. |
| `scraper/content.py` (modify) | `fetch_html(client, map_id, content_id)`. |
| `scraper/converter.py` (modify) | plain fences, admonitions, markdownify fallback. |
| `scraper/tools.py` (new) | Pure tool logic → Markdown strings. |
| `server.py` (new) | `Settings`, `load_settings`, `build_server`, `main`. |
| `main.py` (modify) | `url:` config, shared client/catalog. |
| `tests/` (new) | `conftest.py`, `test_toc_writer.py`, `test_converter.py`, `test_client.py`, `test_catalog.py`, `test_tools.py`, `test_server.py`, `test_cli.py`, `test_live.py`, `fixtures/html/*.html`. |
| `pyproject.toml` (new — dependencies, `dev` dependency group, pytest config, console script); `.github/workflows/ci.yml`, `README.md`, `configs/siemens_tia_openness_v21.yaml` (modify). |
| `requirements.txt` (delete — replaced by `pyproject.toml`). |
| `test_scraper.py` (delete — moved to `tests/`). |

---

### Task 1: pyproject.toml, pytest infrastructure and test migration

**Files:**
- Create: `pyproject.toml`, `tests/__init__.py` (empty), `tests/test_toc_writer.py`, `tests/test_converter.py`
- Modify: `.github/workflows/ci.yml`, `README.md` (Installation section only)
- Delete: `requirements.txt`, `test_scraper.py`

**Interfaces:**
- Produces: dependencies declared only in `pyproject.toml`; `python -m pip install -e . --group dev` installs runtime + dev tools; `pytest` runs from repo root with marker `live` deselected by default; `pip-audit` available.

- [ ] **Step 1: Write `pyproject.toml`** (replaces `requirements.txt`; floors raised to latest releases per Global Constraints)

```toml
[build-system]
requires = ["setuptools>=84.0.0"]
build-backend = "setuptools.build_meta"

[project]
name = "siemens-docs-mcp"
version = "0.1.0"
description = "Search and read Siemens Fluid Topics documentation via MCP or export it to Markdown"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.28.1",
    "beautifulsoup4>=4.15.0",
    "markdownify>=1.2.3",
    "PyYAML>=6.0.3",
    "lxml>=6.1.3",
]

[dependency-groups]
dev = ["pytest>=9.1.1", "ruff>=0.16.10", "pip-audit>=2.10.1"]

[tool.setuptools]
packages = ["scraper"]
py-modules = ["main"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = '-m "not live"'
markers = ["live: hits real Fluid Topics hosts (run with: pytest -m live)"]
```
Before writing, re-check each floor with `python -m pip index versions <pkg>` and use the newest release if it moved. `git rm requirements.txt`.

- [ ] **Step 2: Move tests**

Move `test_output_paths` into `tests/test_toc_writer.py` and `test_code_table_is_not_double_spaced` into `tests/test_converter.py`, unchanged (imports stay `from scraper...`). Delete `test_scraper.py`.

- [ ] **Step 3: Run**

Run: `python -m pip install -e . --group dev && python -m pytest -q && python -m pip_audit --skip-editable`
Expected: `2 passed` (the existing converter/path tests must survive the markdownify 1.x / lxml 6 floors; fix code, not tests, if they don't); pip-audit prints `No known vulnerabilities found`. If it reports vulnerabilities, raise the affected floor and re-run; do not ignore.

- [ ] **Step 4: CI and README**

In `.github/workflows/ci.yml`: add `python -m pip install --upgrade pip` before installing (runner pip may predate 25.1 group support); install with `pip install -e . --group dev`; replace the "Verify imports resolve" step with `python -m pytest -q`; add a step `pip-audit --skip-editable`; keep ruff and `python main.py --help`. In `README.md` Installation, replace `pip install -r requirements.txt` with `pip install -e .` (and `pip install -e . --group dev` for development, noting pip ≥ 25.1).

- [ ] **Step 5: Commit**

```bash
git add -A pyproject.toml requirements.txt tests .github/workflows/ci.yml README.md test_scraper.py
git commit -m "build: move dependencies to pyproject.toml and tests to pytest"
```

---

### Task 2: Generalize the converter

**Files:**
- Modify: `scraper/converter.py` (`_render_block` lines 128–196, module docstring lines 1–17)
- Create: `tests/fixtures/html/tia_scl.html`, `tests/fixtures/html/iox_admonition.html`
- Test: `tests/test_converter.py`

**Interfaces:**
- Produces: `html_to_markdown(html: str, title: str) -> str` (signature unchanged).

- [ ] **Step 1: Capture fixtures (one-off, not committed as a script)**

Run in the venv; it saves raw HTML of two real pages:
```python
import httpx, pathlib
out = pathlib.Path("tests/fixtures/html"); out.mkdir(parents=True, exist_ok=True)
for host, query, name in [("docs.tia.siemens.cloud", "Rules for SCL instructions", "tia_scl.html"),
                          ("docs.industrial-operations-x.siemens.cloud", "OPC UA Server Configuration via ST Code Annotation", "iox_admonition.html")]:
    base = f"https://{host}"; c = httpx.Client(follow_redirects=True, timeout=60)
    c.get(base + "/internal/api/webapp/authentication/session")
    t = c.post(base + "/api/khub/clustered-search", json={"query": query, "contentLocale": "en-US", "paging": {"perPage": 1, "page": 1}}).json()["results"][0]["entries"][0]["topic"]
    (out / name).write_text(c.get(f"{base}/api/khub/maps/{t['mapId']}/topics/{t['contentId']}/content", params={"target": "DESIGNED_READER"}).text, encoding="utf-8")
```
Check: `tia_scl.html` contains `p_table_l_code`; `iox_admonition.html` contains `admonition`. If a search returns a different page, pick any page whose HTML has those classes.

- [ ] **Step 2: Write failing tests** in `tests/test_converter.py`

```python
FIX = Path(__file__).parent / "fixtures" / "html"

def test_scl_code_has_no_language_tag():
    md = html_to_markdown(_clean_html(FIX.joinpath("tia_scl.html").read_text("utf-8")), "T")
    assert "```csharp" not in md
    assert "\n```\n" in md or md.count("```") >= 2

def test_admonition_becomes_blockquote():
    html = '<div class="admonition note"><p class="admonition-title">Note</p><p>Body text.</p></div>'
    assert "> **Note:** Body text." in html_to_markdown(html, "T")

def test_iox_fixture_admonition_rendered():
    md = html_to_markdown(_clean_html(FIX.joinpath("iox_admonition.html").read_text("utf-8")), "T")
    assert "> **" in md

def test_unknown_inline_only_tag_not_dropped():
    md = html_to_markdown("<dl><dt>Term</dt><dd>Definition</dd></dl><pre>x = 1\ny = 2</pre>", "T")
    assert "Term" in md and "Definition" in md
    assert "x = 1\ny = 2" in md
```
Also update `test_code_table_is_not_double_spaced`: expected fence opens with ```` ``` ```` not ```` ```csharp ````.
(`_clean_html` is imported from `scraper.content`.)

- [ ] **Step 3: Run** `python -m pytest tests/test_converter.py -q` → FAIL (csharp present, admonition/inline tests fail).

- [ ] **Step 4: Implement in `scraper/converter.py`**

- Both `csharp` fences → plain ```` ``` ````. Update module docstring line "(csharp)".
- In the `div` branch, before `_render_div`: if `"admonition" in classes`, render `_render_admonition(tag)`:
  `def _render_admonition(div: Tag) -> str` — label = text of `.admonition-title` (fallback: first class other than `admonition`, capitalized); body = rendered block children except the title, joined with a space if single paragraph, each line prefixed `> `. Output first line `> **{label}:** {first body line}`.
- Unknown-tag branch (end of `_render_block`): if recursing over Tag children yields nothing but `tag.get_text(strip=True)` is non-empty, return `markdownify(str(tag), heading_style="ATX").strip()` (import `from markdownify import markdownify`). Add `pre` handling explicitly: `name == "pre"` → ```` ```\n{_normalize_code(tag.get_text())}\n``` ````.

- [ ] **Step 5: Run** `python -m pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add scraper/converter.py tests/test_converter.py tests/fixtures/html
git commit -m "feat: generalize converter for non-Openness and IOX pages"
```

---

### Task 3: Per-host client with throttle, session and retry

**Files:**
- Rewrite: `scraper/client.py`
- Modify: `scraper/content.py` (`fetch_html`), `main.py` (`run`, only enough to keep the CLI working with the new client)
- Test: `tests/test_client.py`

**Interfaces:**
- Produces:
  - `class FluidtopicsError(Exception)` with attribute `status: int | None`.
  - `FluidtopicsClient(host: str, min_interval: float = 0.3, *, transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep)`; context manager; `host` property.
  - `list_maps() -> list[dict]` (GET `/api/khub/maps`, 120 s timeout)
  - `get_pages(map_id: str) -> dict`
  - `get_content(map_id: str, content_id: str) -> str` (param `target=DESIGNED_READER`)
  - `search(query: str, locale: str, filters: list[dict] | None = None, page: int = 1, per_page: int = 10) -> dict` (POST `/api/khub/clustered-search`, body keys `query`, `contentLocale`, `paging{page, perPage}`, `filters` only if non-empty)
  - `scraper.content.fetch_html(client: FluidtopicsClient, map_id: str, content_id: str) -> str`

- [ ] **Step 1: Write failing tests** in `tests/test_client.py`, using `httpx.MockTransport` and a fake clock:

```python
class FakeClock:
    def __init__(self): self.t = 0.0; self.sleeps = []
    def clock(self): return self.t
    def sleep(self, s): self.sleeps.append(s); self.t += s

def test_throttle_spaces_requests():   # session + 2 calls; sleeps == [0.3, 0.3] (approx)
def test_search_body_shape():          # captured JSON == {"query": "q", "contentLocale": "en-US", "paging": {"page": 1, "perPage": 10}}; with filters → "filters" present
def test_401_reestablishes_session_once():   # handler: first content call 401, then 200 → returns text; session endpoint hit twice
def test_403_twice_raises():           # FluidtopicsError, .status == 403
def test_429_honours_retry_after():    # Retry-After: 5 → clock.sleeps contains 5.0; second response 200
def test_retry_after_capped_at_30():   # Retry-After: 120 → sleeps contains 30.0
def test_503_then_fail_raises():       # two 503 → FluidtopicsError(status=503); sleeps contains 2.0
def test_network_error_wrapped():      # transport raises httpx.ConnectError → FluidtopicsError(status=None), message contains host
```

- [ ] **Step 2: Run** `python -m pytest tests/test_client.py -q` → FAIL (import errors).

- [ ] **Step 3: Implement `scraper/client.py`**

Structure: `_send(method, path, **kw)` = throttle + `httpx.Client.request`, converting `httpx.TransportError` to `FluidtopicsError(None, f"network error contacting {host}: {exc}")`. `_request(method, path, **kw)` = ensure session, `_send`, then the retry rules from Global Constraints, then `FluidtopicsError(status, f"{method} {path} -> HTTP {status}")` on remaining non-2xx. Throttle:
```python
with self._lock:
    wait = self._last + self._min_interval - self._clock()
    if wait > 0:
        self._sleep(wait)
    self._last = self._clock()
```
Initialize `self._last = -inf` so the first request does not wait. Remove the old `import time` / `time.sleep` from `get_content`. Keep `_DEFAULT_HEADERS`.

- [ ] **Step 4: Adapt callers**

`fetch_html(client, map_id, content_id)`; log message uses `content_id`. In `main.run`: `host = urlparse(api_base).hostname`; `FluidtopicsClient(host)`; `client.get_pages(map_id)`; `fetch_html(client, map_id, page.content_id)`.

- [ ] **Step 5: Run** `python -m pytest -q && python main.py configs/siemens_tia_openness_v21.yaml --dry-run --page cybersecurity-information` → tests pass; dry run lists 1 page.

- [ ] **Step 6: Commit**

```bash
git add scraper/client.py scraper/content.py main.py tests/test_client.py
git commit -m "feat: per-host Fluid Topics client with throttle and retry"
```

---

### Task 4: Catalog — map list, URL resolution, canonicalization, TOC cache

**Files:**
- Create: `scraper/catalog.py`, `tests/conftest.py`, `tests/test_catalog.py`
- Modify: `scraper/toc.py` (add `find_path`)

**Interfaces:**
- Consumes: `FluidtopicsClient.list_maps/get_pages` (Task 3), `parse_toc`, `TocPage` (`scraper/toc.py`).
- Produces:
  - `scraper.toc.find_path(root: TocPage, content_id: str) -> list[TocPage] | None` — root→node path, DFS.
  - `class CatalogError(ValueError)`
  - `@dataclass(frozen=True) MapInfo: id, title, locale, product, version, version_key, pretty_url, cluster_id, last_publication` (all `str`; `version_key` is `"tia:SoftwareVersionFilter"` or `"SoftwareVersion"` or `""`; `pretty_url` is the `ft:prettyUrl` value without leading `/r/`).
  - `@dataclass(frozen=True) Resolved: host: str, map_id: str, content_id: str | None`
  - `Catalog(hosts: Sequence[str], client_factory: Callable[[str], FluidtopicsClient], ttl_seconds: float = 86400, clock: Callable[[], float] = time.monotonic)`
    - `hosts: tuple[str, ...]` (lower-cased)
    - `client(host: str) -> FluidtopicsClient` (checks allowlist, lazily creates, reuses)
    - `maps(host: str) -> dict[str, MapInfo]` (TTL-cached)
    - `canonical(host: str, field: Literal["product", "locale"], value: str) -> str`
    - `canonical_version(host: str, value: str) -> tuple[str, str]` → `(filter_key, exact_value)`; search `tia:SoftwareVersionFilter` values first, then `SoftwareVersion`
    - `filter(host, product=None, version=None, locale=None, title_contains=None) -> list[MapInfo]` sorted by title
    - `toc(host: str, map_id: str) -> TocPage` (TTL-cached per map)
    - `resolve(url: str) -> Resolved`
    - `reader_url(host: str, map_id: str, page: TocPage) -> str` → `https://{host}{page.pretty_url}` if set, else `https://{host}/r/{map_id}/{page.content_id}`
  - `tests/conftest.py`: `make_map(id, title, locale="en-US", product="STEP 7", version="V21", pretty="en-us/v21/doc", version_key="tia:SoftwareVersionFilter") -> dict` (raw API shape with `metadata[{key, values}]`), `make_toc(...)`, and `FakeClient` (attributes `maps`, `pages: dict[map_id, dict]`, `contents: dict[(map_id, content_id), str]`, `search_response`, records `search_calls`), plus fixtures `fake_tia` and `fake_iox` (one `FakeClient` per host, each with a few maps; one IOX map with `version_key="SoftwareVersion"`, version `6.1`; each with one map's `pages` and `contents` filled), `catalog` (built over both hosts with `client_factory` returning `fake_tia` / `fake_iox`), and `catalog_with_clock` (same, plus a mutable fake clock exposed as `.clock_value`). Tasks 5–7 extend these fixtures rather than defining new clients.

MapInfo field sources (spec §3.2): `product` ← `Product`; `version` ← `tia:SoftwareVersionFilter` else `SoftwareVersion`; `locale` ← `ft:locale`; `pretty_url` ← `ft:prettyUrl`; `cluster_id` ← `ft:clusterId`; `last_publication` ← `ft:lastPublication`; missing → `""`.

- [ ] **Step 1: Write failing tests** in `tests/test_catalog.py`

```python
def test_maps_parsed_from_metadata(catalog): ...            # MapInfo fields for a TIA and an IOX map
def test_maps_cached_until_ttl(catalog_with_clock): ...      # list_maps called once; again after clock += 86401
def test_unknown_host_rejected(catalog): ...                 # CatalogError; message lists both allowed hosts
def test_resolve_short_map_url(catalog): ...                 # /r/{mapId} → Resolved(host, mapId, None)
def test_resolve_short_topic_url(catalog): ...               # /r/{mapId}/{contentId} → content_id set
def test_resolve_pretty_map_url(catalog): ...                # https://host/r/en-us/v21/doc → map root
def test_resolve_pretty_topic_url(catalog): ...              # longest ft:prettyUrl prefix, then TOC prettyUrl match
def test_resolve_longest_prefix_wins(catalog): ...           # maps "en-us/v21/doc" and "en-us/v21/doc-extra"
def test_resolve_tolerates_url_noise(catalog): ...           # ?q=1, #frag, trailing /, http://, upper-case host → same Resolved
def test_resolve_unknown_path(catalog): ...                  # CatalogError mentioning search_docs and list_publications
def test_canonical_product_case_insensitive(catalog): ...    # "step 7" → "STEP 7"
def test_canonical_unknown_suggests_close(catalog): ...      # "STEP7" → CatalogError containing "STEP 7"
def test_canonical_locale_case_insensitive(catalog): ...     # "en-us" → "en-US"
def test_canonical_version_uses_source_key(catalog): ...     # TIA "v21" → ("tia:SoftwareVersionFilter", "V21"); IOX "6.1" → ("SoftwareVersion", "6.1")
def test_filter_combines_and_sorts(catalog): ...             # product+version+locale+title_contains
def test_find_path_returns_root_to_node(): ...
```

- [ ] **Step 2: Run** `python -m pytest tests/test_catalog.py -q` → FAIL (import errors).

- [ ] **Step 3: Implement `find_path` and `scraper/catalog.py`**

Canonicalization: case-insensitive equality against the distinct non-empty values for that field across `maps(host)`; no match → `CatalogError(f"Unknown {field} {value!r} on {host}. Close matches: {difflib.get_close_matches(value, values, n=5, cutoff=0.5)}")` (when no close matches, list up to 10 known values).

Resolve algorithm:
1. `urlsplit`; host = `netloc.lower()` minus port; not allowed → `CatalogError` listing `self.hosts`. Path: strip trailing `/`; must start with `/r/`; ignore query/fragment.
2. `parts = path[3:].split("/")`. If `parts[0]` is a map id in `maps(host)`: `Resolved(host, parts[0], parts[1] if len(parts) > 1 else None)`.
3. Else rel = `path[3:].lower()`; candidates = maps whose `pretty_url.lower()` equals rel or is a prefix of `rel + "/"`; take the longest. rel equals it → map root. Otherwise walk `toc(host, map_id)` for a node with `pretty_url.lower() == "/r/" + rel` → its `content_id`.
4. Nothing → `CatalogError(f"Could not resolve {url}. Use search_docs or list_publications to find a valid reader URL.")`.

- [ ] **Step 4: Run** `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add scraper/catalog.py scraper/toc.py tests/conftest.py tests/test_catalog.py
git commit -m "feat: catalog with URL resolution and filter canonicalization"
```

---

### Task 5: Tool logic — `search_docs` and `list_publications`

**Files:**
- Create: `scraper/tools.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `Catalog` (Task 4), `FluidtopicsClient.search` (Task 3).
- Produces (all return Markdown `str`, raise `CatalogError`/`ValueError`/`FluidtopicsError`):
  - `search_docs(catalog: Catalog, query: str, host: str, locale: str, product: str | None = None, version: str | None = None, limit: int = 10) -> str`
  - `list_publications(catalog: Catalog, host: str, locale: str, product: str | None = None, version: str | None = None, title_contains: str | None = None) -> str`

Output formats:
- search: `Found {totalResultsCount} results for "{query}" on {host}. Showing {n}:` then per hit
  `{i}. **{title}** — {mapTitle}{" (" + version + ")" if version}\n   {" > ".join(breadcrumb)}\n   {excerpt}\n   {readerUrl}`; excerpt = `BeautifulSoup(htmlExcerpt).get_text(" ", strip=True)`; version from topic `metadata` (`tia:SoftwareVersionFilter` then `SoftwareVersion`). Use the first `entries[]` item with `type == "TOPIC"` per cluster; skip clusters without one. Zero hits → `No results for "{query}" on {host}.`
- list: per row `- **{title}** — {product} {version} [{locale}] https://{host}/r/{pretty_url}`; footer `Showing 50 of {N} — narrow your filters.` when capped; zero → `No publications match these filters on {host}.`

- [ ] **Step 1: Write failing tests**

```python
def test_search_docs_formats_hits(catalog, fake_tia): ...                 # title, mapTitle, "(V21)", breadcrumb " > ", excerpt without tags, readerUrl
def test_search_docs_canonicalizes_filters(catalog, fake_tia): ...       # product "step 7", version "v21" → filters [{"key":"Product","values":["STEP 7"]},{"key":"tia:SoftwareVersionFilter","values":["V21"]}]
def test_search_docs_version_filter_key_for_iox(catalog, fake_iox): ...  # version "6.1" → key "SoftwareVersion"
def test_search_docs_limit_bounds(catalog): ...                          # limit 0 and 51 → ValueError mentioning "1-50"
def test_search_docs_no_results(catalog, fake_tia): ...                  # exact "No results" line
def test_list_publications_filters_and_cap(catalog): ...                 # 60 maps → 50 rows + footer
def test_list_publications_none(catalog): ...                            # exact "No publications match" line
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `python -m pytest -q` → pass.

- [ ] **Step 5: Commit**

```bash
git add scraper/tools.py tests/test_tools.py tests/conftest.py
git commit -m "feat: search_docs and list_publications tool logic"
```

---

### Task 6: Tool logic — `read_page` and `get_toc`

**Files:**
- Modify: `scraper/tools.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `Catalog.resolve/toc/maps/client/reader_url`, `find_path` (Task 4); `fetch_html` (Task 3); `html_to_markdown` (Task 2).
- Produces:
  - `read_page(catalog: Catalog, url: str, offset: int = 0, max_chars: int = 20000) -> str`
  - `get_toc(catalog: Catalog, url: str, depth: int = 2) -> str`

Behaviour:
- `read_page`: resolve; `content_id is None` → TOC root's `content_id`. Path = `find_path(toc, content_id)`; if None (topic not in the TOC), title = `"(untitled topic)"` and the Path line shows only the publication title. Body = `html_to_markdown(fetch_html(...), title)`. Header (always):
  ```
  > Publication: {map.title} ({map.version}) [{map.locale}]
  > Path: {" > ".join(p.title for p in path)}
  > Source: {reader_url}
  ```
  then blank line, then `body[offset:offset+max_chars]`; if `offset + max_chars < len(body)` append `\n\n[truncated — call again with offset={offset+max_chars}]`. `offset >= len(body) > 0` → `ValueError(f"offset {offset} is past the end of this page (length {len(body)}).")`. Bounds: `offset < 0`, `max_chars` outside 1000–100000 → `ValueError` naming the range.
- `get_toc`: resolve; start node = map root or the node for `content_id`; lines `{"  " * level}- {title} — {reader_url}` for start (level 0) and descendants with level ≤ depth (pre-order). Cap 500 lines, then append `… truncated at 500 lines — use a deeper URL or a smaller depth.` `depth` outside 1–6 → `ValueError`.

- [ ] **Step 1: Write failing tests**

```python
def test_read_page_header_and_body(catalog): ...          # three header lines, H1 title, body text
def test_read_page_map_root_reads_root_topic(catalog): ...
def test_read_page_truncates_with_offset_hint(catalog): ...  # long body, max_chars=1000 → footer "offset=1000"; second call with offset=1000 continues
def test_read_page_offset_past_end(catalog): ...           # ValueError containing "length"
def test_read_page_param_bounds(catalog): ...              # offset -1, max_chars 999 / 100001
def test_get_toc_depth(catalog): ...                       # depth 1 excludes grandchildren
def test_get_toc_subtree_from_topic_url(catalog): ...
def test_get_toc_line_cap(catalog): ...                    # 600-node TOC → 500 lines + note
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `python -m pytest -q` → pass.

- [ ] **Step 5: Commit**

```bash
git add scraper/tools.py tests/test_tools.py tests/conftest.py
git commit -m "feat: read_page and get_toc tool logic"
```

---

### Task 7: MCP server wiring

**Files:**
- Create: `server.py`, `tests/test_server.py`
- Modify: `pyproject.toml` — add `"mcp>=2.3.0,<3"` to `dependencies` (re-check the latest 2.x first); `py-modules = ["main", "server"]`; add
  ```toml
  [project.scripts]
  siemens-docs-mcp = "server:main"
  ```

**Interfaces:**
- Consumes: `scraper.tools.*` (Tasks 5–6), `Catalog` (Task 4), `FluidtopicsClient` (Task 3).
- Produces:
  - `DEFAULT_HOSTS = ("docs.tia.siemens.cloud", "docs.industrial-operations-x.siemens.cloud")`
  - `@dataclass(frozen=True) Settings: hosts: tuple[str, ...], locale: str, min_interval: float`
  - `load_settings(env: Mapping[str, str]) -> Settings` — extra hosts appended after defaults, stripped, lower-cased, de-duplicated preserving order, empties dropped; invalid/negative `SIEMENS_DOCS_MIN_INTERVAL` → `ValueError`.
  - `build_server(catalog: Catalog, settings: Settings) -> MCPServer` — registers tools `search_docs`, `read_page`, `get_toc`, `list_publications`. Tool params as spec §4; `host: str | None = None` → `settings.hosts[0]`; `locale: str | None = None` → `settings.locale`. Each wrapper catches `CatalogError`, `FluidtopicsError`, `ValueError` → `raise ToolError(str(exc))`.
  - `main() -> None` — `settings = load_settings(os.environ)`; `Catalog(settings.hosts, lambda h: FluidtopicsClient(h, settings.min_interval))`; `build_server(...).run()`; guarded by `if __name__ == "__main__":`.

Tool docstrings (the agent reads these) must state: what the tool returns; that reader URLs from any result or page link are valid input to `read_page`/`get_toc`; for `search_docs`/`list_publications` that `product` and `version` are matched against the catalog (examples: `STEP 7`, `WinCC Unified`, `SIMATIC AX`; `V21`, `6.1`) and that `list_publications` shows valid values; the allowed hosts.

- [ ] **Step 1: Write failing tests** (`@pytest.mark.anyio`, `from mcp import Client`)

```python
def test_load_settings_defaults(): ...            # hosts == DEFAULT_HOSTS, locale "en-US", min_interval 0.3
def test_load_settings_extra_hosts(): ...          # " Docs.Example.com ,docs.tia.siemens.cloud," → DEFAULT_HOSTS + ("docs.example.com",)
def test_load_settings_bad_interval(): ...         # "-1" and "abc" → ValueError
async def test_tools_registered(server): ...        # {t.name for t in (await client.list_tools()).tools} == the 4 names
async def test_unknown_host_is_tool_error(server): ...  # call read_page url="https://evil.example/r/x" → is_error, text contains "docs.tia.siemens.cloud"
async def test_search_defaults_host_and_locale(server, fake_tia): ...  # call search_docs {"query": "x"} → FakeClient saw locale "en-US" on default host
```
`server` fixture = `build_server(catalog_from_conftest, Settings(DEFAULT_HOSTS, "en-US", 0.0))`.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (update `pyproject.toml`, then `python -m pip install -e . --group dev`). **Step 4: Run** `python -m pytest -q` → pass.

- [ ] **Step 5: Dependency audit and smoke check**

Run: `python -m pip_audit --skip-editable` → `No known vulnerabilities found` (new dependency `mcp` and its transitive deps).
Run: `python -c "import server; print('ok')"` → `ok` (import must not start the server).
Run (PowerShell): `Get-Command siemens-docs-mcp` → resolves to the venv `Scripts` folder (console script installed).

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server.py pyproject.toml
git commit -m "feat: MCP server exposing Fluid Topics docs tools"
```

---

### Task 8: CLI `url:` config, live smoke tests, README

**Files:**
- Modify: `main.py` (`_validate_config`, `run`, module docstring), `configs/siemens_tia_openness_v21.yaml`, `README.md`
- Create: `tests/test_cli.py`, `tests/test_live.py`

**Interfaces:**
- Consumes: `Catalog.resolve` (Task 4), `FluidtopicsClient` (Task 3), `build_server`/tools (Tasks 5–7).
- Produces: config accepts `url` + `output_dir` (new form) or `api_base` + `map_id` + `output_dir` (legacy); `base_url` no longer required.

- [ ] **Step 1: Write failing tests** in `tests/test_cli.py`

```python
def test_validate_config_accepts_url_form(): ...      # {"url": "...", "output_dir": "o"} ok
def test_validate_config_accepts_legacy_form(): ...   # {"api_base": ..., "map_id": ..., "output_dir": ...} ok
def test_validate_config_rejects_neither(): ...       # ValueError naming "url" and "api_base + map_id"
def test_resolve_target_from_url(monkeypatch): ...    # url → (host, map_id) via a Catalog built on FakeClient
```
Expose `main._resolve_target(config: dict, catalog_factory: Callable[[str], Catalog]) -> tuple[str, str]` returning `(host, map_id)`; for `url`, the catalog is built with `hosts=[urlparse(url).hostname]` (CLI trusts its own config); a topic URL exports its whole publication and logs a warning.

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** and switch `configs/siemens_tia_openness_v21.yaml` to `url: "https://docs.tia.siemens.cloud/r/en-us/v21/tia-portal-openness-api-for-automation-of-engineering-workflows"` + `output_dir`, removing the DevTools comment block.

- [ ] **Step 4: Live tests** in `tests/test_live.py`, each `@pytest.mark.live`, parametrized over both default hosts: `search_docs` (query `"OPC UA"` for IOX, `"export block"` for TIA) returns ≥1 hit → `read_page(first readerUrl)` contains `> Source:` → `get_toc(same url, depth=1)` has ≥1 line.

Run: `python -m pytest -m live -q` → `2 passed` (needs network).
Run: `python main.py configs/siemens_tia_openness_v21.yaml --dry-run --page cybersecurity-information` → 1 page listed.

- [ ] **Step 5: README**

Replace "Adding a new documentation site / Step 1 — Find the map_id" with the `url:` form; add an "MCP server" section: install, the four tools, env vars table (Global Constraints), and a Claude Code registration example:
```bash
claude mcp add siemens-docs -- <repo>/.venv/Scripts/siemens-docs-mcp
```
(console script from `pyproject.toml`; on Linux/macOS `<repo>/.venv/bin/siemens-docs-mcp`).
Update the configuration reference table (`url` or legacy `api_base`+`map_id`). State that the cache is in-memory and the first call per host takes a few seconds.

- [ ] **Step 6: Full check**

Run: `ruff check . && python -m pytest -q && python -m pip_audit --skip-editable` → clean, all pass, no known vulnerabilities.

- [ ] **Step 7: Commit**

```bash
git add main.py configs/siemens_tia_openness_v21.yaml README.md tests/test_cli.py tests/test_live.py
git commit -m "feat: CLI accepts reader URL; add live smoke tests and MCP docs"
```
