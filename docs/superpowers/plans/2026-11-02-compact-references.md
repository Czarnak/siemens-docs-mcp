# Compact References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Checked steps below record completed execution.

**Goal:** Deliver stateless, host-qualified compact references across the four existing MCP tools, after a separately verified behavior-preserving rendering refactor.

**Architecture:** Extend the existing catalog's reference boundary and reuse `Resolved`, `MapInfo`, and `TocPage`. Tool functions validate, retrieve, and prepare values; deterministic rendering functions produce Markdown without I/O. Keep the current converter and exporter architecture.

**Tech Stack:** Python >=3.11; existing MCP SDK, BeautifulSoup, pytest, pytest-cov, and Ruff. No dependency changes.

**Spec:** [Approved compact-reference design](../specs/2026-11-01-compact-references-design.md), approved 2026-11-02.

## Global Constraints

- Keep the existing four tool names and current required parameter names.
- `read_page(url=...)` and `get_toc(url=...)` accept reader URLs and compact references; keep `url` as the parameter name.
- Stable prefixes: `tia` = `docs.tia.siemens.cloud`; `iox` = `docs.industrial-operations-x.siemens.cloud`. Additional allowed hosts use their full hostname as prefix.
- Publication references are `<prefix>:<mapId>`; topic references are `<prefix>:<mapId>/<contentId>`.
- Prefixes are case-insensitive and emitted lowercase; identifiers retain case. Trim surrounding whitespace only.
- Identifier segments use the existing `[\w~.-]+` character set and cannot be `.` or `..`; reject empty/extra segments, queries, fragments, and percent-encoded compact paths.
- Add `reference_format="compact"|"url"`, default `compact`, to all four tools. Only tool-generated address fields change representation; page-body links remain unchanged.
- Preserve ordering, limits, content fields, provenance, pagination, URL parsing behavior, informative errors, throttling, and central MCP error translation.
- Reject invalid compact syntax/hosts and invalid output formats before fetching. Formatting a known compact target performs no metadata/TOC fetch.
- No session handles, new tools, scope filters, section/code modes, batching, persistence, alias configuration, generic renderer framework, converter changes, or compact CLI configuration.
- Record characters; do not claim measured tokens without naming the tokenizer. Live unavailability is an evidence gap, never an offline success claim.
- Read both this plan and the approved spec before execution. Approval of the design and plan does not itself request implementation.

## Review Focus

1. The same map/topic IDs on different hosts must remain distinct after host reordering and a new catalog instance: Task 3.
2. Incomplete or malformed search identities must preserve result content without fabricated references or extra TOC fetches: Task 4.
3. A valid topic absent from the TOC must retain the existing direct-read fallback; a tocId alias must resolve to the canonical contentId: Tasks 3-4.
4. Invalid format values and compact references must cause zero client requests, including content requests: Tasks 1, 3-4.
5. Old named `url` arguments, explicit URL output, and URL-based CLI export must remain usable after compact defaults ship: Tasks 2 and 4.

## File map and execution order

| File | Responsibility/change | Task |
| --- | --- | --- |
| `tests/conftest.py` | Configurable coherent search identities; content-call observability; fixed output cases | 1 |
| `tests/fixtures/reference_outputs.json` | Reviewed legacy outputs and deterministic character counts | 1 |
| `tests/fixtures/reference_live_targets.json` | Real targets pinned during the baseline, or an explicitly empty discovery result | 1, 5 |
| `tests/test_reference_sizes.py` | Legacy characterization, semantic checks, fixed size ceilings | 1, 5 |
| `siemens_docs_mcp/rendering.py` | Pure Markdown formatting and the small normalized search-hit record | 2 |
| `tests/test_rendering.py` | Formatting/content tests independent of catalog/client access | 2 |
| `siemens_docs_mcp/catalog.py` | Alias mapping, compact parsing/spelling, existing URL compatibility | 3 |
| `tests/test_catalog.py` | Reference grammar, allowlist, identity, URL regressions | 3 |
| `siemens_docs_mcp/tools.py` | Normalization, validation, reference selection, renderer orchestration | 2, 4 |
| `siemens_docs_mcp/server.py` | Shared host defaults and format parameter/schema wiring | 3, 4 |
| `tests/test_tools.py`, `tests/test_server.py` | Tool/MCP contracts, round trips, no-fetch checks | 2, 4 |
| `tests/test_live.py` | Pin/read fixed live targets and print before/after measurements | 1, 4, 5 |
| `README.md` | Compact defaults, examples, URL escape hatch, CLI scope | 4 |
| `docs/superpowers/plans/2026-11-02-compact-references-evidence.md` | Baseline/candidate identities, fixture/live results, qualification gaps | 1, 5 |

Do Tasks 1-5 sequentially: they share interfaces and the baseline. Parallelize only read-only inspection/review. At execution time inspect the checkout, instructions, and unrelated changes, and use the worktree workflow where isolation is needed. Worktree creation is not required merely to read this plan.

Commands below use PowerShell from the repository root and the verified local `.venv` executables. If that environment is replaced, use the project's documented environment setup rather than installing new dependencies ad hoc.

### Task 1: Capture a trustworthy baseline and fix fixture observability

**Files:** Modify `tests/conftest.py:69-100,191-216`, `tests/test_live.py`; create the three fixture/measurement files and evidence document listed above. No production changes.

**Interfaces:**
- Extend `make_hit` with keyword-only `map_id: str | None = "tia2"` and `content_id: str | None = "tia2-p1"`; retain existing arguments. Omit the corresponding raw API key when an explicit `None` is supplied. Use a coherent default `reader_url` for `tia2-p1`; IOX tests supply an IOX URL and IDs explicitly.
- Add `FakeClient.get_content_calls: list[tuple[str, str]]`, appended by `get_content` before lookup.
- Add pytest fixture `reference_cases -> dict[str, tuple[str, dict]]`: eight small cases specify an existing tool name and keyword arguments for the shared `catalog`, covering search/list/read/TOC for both hosts. Supply minimal TOC and HTML content for every listed publication and emitted node used by round-trip tests. Keep the separate long-TOC fixture out of this eight-case golden-output mapping.
- Live manifest shape: `{"targets": [{"host": str, "query": str, "publication_url": str, "topic_url": str}]}`. An empty list means discovery did not succeed; record the reason in evidence.

- [x] **Step 1: Add fixture contract tests** to `tests/test_reference_sizes.py`:

```python
def test_search_fixture_identity_is_configurable():
    topic = make_hit(map_id="iox1", content_id="iox1-p1")["entries"][0]["topic"]
    assert (topic["mapId"], topic["contentId"]) == ("iox1", "iox1-p1")
    assert "contentId" not in make_hit(content_id=None)["entries"][0]["topic"]

def test_content_calls_are_recorded(fake_tia):
    fake_tia.get_content("tia2", "tia2-p1")
    assert fake_tia.get_content_calls == [("tia2", "tia2-p1")]
```

- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_reference_sizes.py -q`. Expect the new assertions to fail because configurable identities/content counters do not exist.
- [x] **Step 3: Implement the fixture changes.** Update existing tests that explicitly depend on the previous synthetic `c1` or default URL. Keep the existing TOPIC-cluster response shape; do not introduce a second fake client. Populate root/chapter bodies where publication/TOC round trips require them.
- [x] **Step 4: Capture unchanged production outputs** for `reference_cases`, once, into `tests/fixtures/reference_outputs.json`, keyed by case name with `output` and `chars`. Review titles, addresses, ordering, pagination, and excerpts. Add `test_legacy_output_baselines` asserting `actual == recorded[case]["output"]` and `len(actual) == recorded[case]["chars"]`. No automatic golden-file regeneration during tests.
- [x] **Step 5: Add a fixed long-path TOC case** with 300 children plus a root, depth 1, at least a 160-character human-readable path per child, and valid stable IDs. Record its baseline character count, but do not store hundreds of repetitive full lines. Assert the expected row count and every fixture topic ID through URL resolution. Use a separate map so this case cannot overwrite the small round-trip fixtures.
- [x] **Step 6: Capture the live baseline when reachable.** Extend the existing `test_search_read_toc_roundtrip` workflow to discover one successful TIA Openness target and one IOX target, then record their actual publication/topic URLs and fixed queries in the manifest using the normal file-edit tool. Never invent target IDs. Use those targets for `test_fixed_target_measurements`, printing host, target, tool, character count, identity set, and cache/request conditions. Run `.\.venv\Scripts\python.exe -m pytest -m live -q -s`; record failures if discovery/measurement is unavailable. Do not replace a missing fixed-target measurement with another changing search result silently.
- [x] **Step 7: Verify** `.\.venv\Scripts\python.exe -m pytest tests/test_reference_sizes.py tests/test_tools.py tests/test_server.py tests/test_cli.py -q`. Expect all offline tests to pass and characterization to match unchanged production output. Record the starting commit, fixture measurements, exact live targets/results or gaps in the evidence document.
- [x] **Step 8: Review and commit only Task 1 files** with `test: capture reference output baselines`. Resolve all named paths before staging; do not include unrelated user files. Run `git diff --check` before committing.

### Task 2: Extract pure rendering without changing behavior

**Files:** Create `siemens_docs_mcp/rendering.py`, `tests/test_rendering.py`; modify `siemens_docs_mcp/tools.py:27-169`. Keep server schemas and tool defaults unchanged.

**Interfaces:** The new module defines a frozen `SearchHit` dataclass with `title: str`, `map_title: str`, `version: str`, `breadcrumb: tuple[str, ...]`, `excerpt: str`, and `reference: str`, plus these functions:

```python
render_search(query: str, host: str, total: int, hits: Sequence[SearchHit]) -> str
render_publications(host: str, rows: Sequence[tuple[MapInfo, str]], total: int, limit: int) -> str
render_page(publication: MapInfo, path: Sequence[str], source: str, chunk: str) -> str
render_toc(rows: Sequence[tuple[int, str, str]], truncated: bool, limit: int) -> str
```

In `tools.py`, `_normalize_hit(topic: dict, reference: str) -> SearchHit` owns version extraction, HTML excerpt cleanup, and breadcrumb normalization. These are internal Python interfaces, not new MCP tools. TOC rows are `(level, title, reference)`; pass at most the existing cap and an explicit truncation flag. Pagination, source selection, and metadata lookup stay in tools.

- [x] **Step 1: Add failing renderer tests** for all four functions. Pin the exact existing strings from Task 1, including empty results, missing version, hyphenated excerpts, breadcrumb spacing, provenance, and cap messages. Representative search assertion:

```python
hit = SearchHit("Hit", "Manual", "V21", ("A", "B"), "Some text", "https://example.test/r/m/c")
assert render_search("q", "example.test", 1, [hit]) == (
    'Found 1 results for "q" on example.test. Showing 1:\n'
    '1. **Hit** — Manual (V21)\n   A > B\n   Some text\n   https://example.test/r/m/c'
)
```

- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_rendering.py -q`. Expect import/missing-symbol failure before the module exists.
- [x] **Step 3: Extract the formatting functions and normalization.** Reuse `MapInfo` for publication fields; no page-result hierarchy. Renderers receive strings/records only, never `Catalog` or a client. Preserve every legacy string, including URL-oriented hints during this structural step. Keep `fetch_html`, `html_to_markdown`, offset slicing, limit validation, and error ownership unchanged.
- [x] **Step 4: Route existing tool outputs through the renderers.** Keep existing URL generation in orchestration; no `reference_format` parameter yet. Cover `test_renderer_does_not_access_catalog`: renderer tests run from prepared values while catalog/client entry points are patched to raise if called.
- [x] **Step 5: Verify** `.\.venv\Scripts\python.exe -m pytest tests/test_rendering.py tests/test_reference_sizes.py tests/test_tools.py tests/test_server.py tests/test_cli.py -q`, then `.\.venv\Scripts\ruff.exe check .`. Expect exact Task 1 outputs, unchanged schemas/defaults, all selected tests passing, and no Ruff diagnostics. Existing CLI tests include URL/legacy configuration and topic-URL warning behavior.
- [x] **Step 6: Review and commit** the Task 2 files with `refactor: separate documentation rendering from retrieval`. This is the independent stage A checkpoint. Do not combine its commit with compact-default changes.

### Task 3: Extend the catalog's reference boundary

**Files:** Modify `siemens_docs_mcp/catalog.py:20-47,198-255`, `siemens_docs_mcp/server.py:20`, `tests/test_catalog.py`.

**Interfaces:** In `catalog.py`, define `HOST_ALIASES = {"tia": "docs.tia.siemens.cloud", "iox": "docs.industrial-operations-x.siemens.cloud"}` and `ReferenceFormat = Literal["compact", "url"]`. Derive existing `server.DEFAULT_HOSTS` from that mapping in the same order, preserving its tuple value. Add:

```python
validate_reference_format(value: str) -> ReferenceFormat
Catalog.compact_ref(self, target: Resolved) -> str
Catalog.id_url(self, target: Resolved) -> str
Catalog.fallback_reader_url(self, value: object) -> str | None
Catalog._parse_compact_ref(self, value: str) -> Resolved
```

Keep `Catalog.resolve(self, url: str) -> Resolved`, `map_url`, and `reader_url` signatures. `compact_ref` validates host/identifier syntax without loading maps/TOCs. `id_url` checks the allowed host and assembles the existing ID-URL spelling without I/O or new restrictions on legacy targets. `fallback_reader_url` is a no-I/O check of an upstream search URL: return the stripped string only for HTTPS, an allowed hostname, no credentials, and a nonempty `/r/` path; otherwise return `None`. This fallback check does not tighten legacy URL inputs to `resolve`.

- [x] **Step 1: Add failing reference tests.** Include the following exact assertions plus a parameterized grammar matrix:

```python
assert catalog.resolve(" TIA:tia2/tia2-p1 ") == Resolved(TIA_HOST, "tia2", "tia2-p1")
assert catalog.resolve("iox:iox1").content_id is None
assert catalog.compact_ref(Resolved(TIA_HOST, "Ab~.-_1", "Cd2")) == "tia:Ab~.-_1/Cd2"
assert catalog.id_url(Resolved(IOX_HOST, "iox1", None)) == f"https://{IOX_HOST}/r/iox1"
```

`test_compact_syntax_rejected_before_fetch` covers `tia:`, `tia:/c`, `tia:m/`, `tia:m/c/x`, `tia:m//c`, `tia:../c`, `tia:m/.`, `tia:m/%2F`, `tia:m?x=1`, `tia:m/c#h`, internal spaces, unknown prefixes, and disallowed literal hosts. Before and after each call, assert both clients' `list_maps_calls`, `get_pages_calls`, `get_content_calls`, and `search_calls` are unchanged. Test valid Unicode word characters consistently with the existing regex; do not silently switch to ASCII.

- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_catalog.py -q`. Expect failures limited to the new contract before implementation.
- [x] **Step 3: Implement compact parsing before URL parsing.** Values containing `://` or starting with `//` continue through the existing URL branch; other values use the strict compact grammar. Validate syntax/prefix before map lookup, then verify publication existence through normal catalog behavior. Preserve arbitrary syntactically valid topic IDs for the existing direct-read fallback. Reuse `Resolved`; do not preload a TOC for an ID reference. Add `test_protocol_relative_reader_url_is_preserved` asserting that `//docs.tia.siemens.cloud/r/tia2/tia2-p1` still resolves as before.
- [x] **Step 4: Implement spelling and the fallback check.** Use aliases for built-ins and literal hostnames otherwise; accept both forms for allowed hosts. Delegate existing ID-URL fallbacks in `map_url`/`reader_url` to `id_url` without changing pretty-URL ambiguity handling. `validate_reference_format` rejects anything except the two exact lowercase values with a useful `ValueError`.
- [x] **Step 5: Add identity/no-I/O tests.** `test_prefix_identity_survives_restart_and_host_order` uses fresh catalogs, reversed host order, and identical map/topic IDs on both hosts; assert host-specific `Resolved` results. `test_literal_host_roundtrip` covers both built-ins and one allowed extra host. `test_compact_spelling_does_not_fetch` patches client factory/maps/TOC access to raise while formatting known targets. `test_upstream_url_fallback` covers valid URLs, missing/non-string values, foreign hosts, empty reader paths, credentials, and non-HTTPS schemes.
- [x] **Step 6: Verify** `.\.venv\Scripts\python.exe -m pytest tests/test_catalog.py tests/test_server.py tests/test_reference_sizes.py -q` and `.\.venv\Scripts\ruff.exe check .`. Existing pretty-URL ambiguity, unknown-host, filter, cache, and URL characterization tests must still pass; defaults remain URL output until Task 4.
- [x] **Step 7: Review and commit** with `feat: support stateless compact documentation references`.

### Task 4: Deliver compact defaults through tools and MCP schemas

**Files:** Modify `siemens_docs_mcp/tools.py`, `siemens_docs_mcp/server.py:24-118`, `tests/test_tools.py`, `tests/test_server.py`, `tests/test_reference_sizes.py`, `tests/test_live.py`, and `README.md`. Adjust rendering hints only where they must mention references.

**Interfaces:** Add keyword-only `reference_format: ReferenceFormat = "compact"` after the existing parameters on all four functions in `tools.py`. Append the same optional parameter to the four MCP wrappers and forward it by name. Preserve all existing positional parameters and required `url` names. Add `_search_reference(catalog: Catalog, host: str, topic: dict, reference_format: ReferenceFormat) -> str` in `tools.py` for upstream hit preparation; it feeds Task 2's `_normalize_hit` and renderers.

- [x] **Step 1: Add failing behavior/schema tests.** Representative assertions:

```python
assert "> Source: tia:tia2/tia2-p1" in read_page(catalog, url="tia:tia2/t-p1")
assert "Hello" in read_page(catalog, url="tia:tia2/tia2-p1")
assert "> Source: https://" in read_page(catalog, url="tia:tia2/tia2-p1", reference_format="url")
```

For each tool returned by `(await client.list_tools()).tools`, assert `tool.input_schema["properties"]["reference_format"]` has `enum == ["compact", "url"]` and `default == "compact"`. Assert `read_page`/`get_toc` still require `url`, never a replacement `ref` parameter, and that the tool-name set is unchanged. Use the existing `Client(server)` and `result.is_error`/`result.content[0].text` test pattern.

- [x] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_server.py -q`. Expect new-parameter/default/schema assertions to fail before wiring.
- [x] **Step 3: Validate the format before any catalog/client lookup.** Prepare compact strings from known identities and URL strings through existing catalog helpers; pass only the selected spelling to renderers. Replace `read_page`'s inline fallback URL construction with `Catalog.id_url`. Preserve canonical contentId selection for tocId inputs, TOC subtree selection, publication-only root behavior, pagination, and body links. For a synthetic multi-section TOC root with an empty content ID, prepare `Resolved(host, map_id, None)` and emit the publication reference; never emit an empty topic segment. Pin this in `test_multi_root_toc_uses_publication_reference` for IOX in both formats.
- [x] **Step 4: Implement search reference preparation.** For valid map/content IDs, compact mode uses `compact_ref` and never resolves each hit through a TOC. URL mode preserves a valid upstream reader URL, using `id_url` if IDs are valid but the URL is unavailable. Missing/invalid identities use `fallback_reader_url`; if neither route succeeds, render the literal `(reference unavailable)` while retaining title/excerpt/breadcrumb. Never emit malformed IDs or silently drop the hit. Keep format validation outside any per-hit fallback handling.
- [x] **Step 5: Pin fallback and request behavior.** Add `test_search_reference_fallbacks` for absent, `None`, wrong-type, empty, and invalid-segment IDs; valid/invalid/foreign/missing URLs; and fully unaddressable hits. Assert correct spelling or marker plus unchanged visible content. `test_search_does_not_fetch_hit_tocs` asserts zero new TOC/content requests. `test_invalid_format_rejected_before_fetch` covers all four direct tools and an MCP call with `reference_format="json"`, checking all fake-client counters are unchanged.
- [x] **Step 6: Add round trips and compatibility.** Parameterize both hosts and both formats. Extract emitted references from fixture search/list/TOC/source fields and pass them to read/TOC as appropriate, asserting the expected publication/topic identity and content. Include same-ID cross-host collisions, tocId aliases, publication-only reads, and `test_read_topic_absent_from_toc`: add HTML for `tia2/orphan`, assert direct reading succeeds and its source uses the chosen format. Preserve the existing TOC rejection for an orphan subtree. Keep URL mode equal to Task 1's golden outputs for well-formed fixtures.
- [x] **Step 7: Wire MCP schemas and update callers/docs in the same change.** Extend descriptions/README with both compact forms, stable host aliases/literal hosts, unchanged `url` arguments, `reference_format="url"`, and the fact that body links/CLI configuration remain as before. Do not perform the separate milestone 5 description slimming. Update live reference extraction to accept compact defaults, and explicitly request URL output in legacy baseline tests and legacy live measurements; the golden data itself must not change to hide a regression.
- [x] **Step 8: Verify** `.\.venv\Scripts\python.exe -m pytest tests/test_tools.py tests/test_server.py tests/test_catalog.py tests/test_rendering.py tests/test_reference_sizes.py tests/test_cli.py -q`, then `.\.venv\Scripts\ruff.exe check .`. Re-run existing CLI tests for URL config, legacy config, topic warning, and URL precedence. Expected: all pass, exactly four MCP tools, compact defaults, and explicit URL mode reproducing valid legacy output.
- [x] **Step 9: Review and commit** with `feat: emit compact references across documentation tools`.

### Task 5: Freeze size budgets and qualify the candidate

Execution status (2026-11-02): All five tasks are implemented and independently
task-reviewed, with stage A independently committed at `802c769`. Qualification
commit `bb9ef38` records measurements of its production parent `a83b3e9`:
291 offline tests, 4 live tests, 99% statement coverage, and clean Ruff.
The [qualification evidence](2026-11-02-compact-references-evidence.md#task-5-candidate-qualification-2026-11-02)
records the exact measurements and the verified TIA publication/root equivalence.
Whole-branch independent review found no Critical or Important issues and one
minor stale-handoff documentation finding, addressed in this correction. The
correction still requires scoped review; no release is authorized.

**Files:** Modify `tests/test_reference_sizes.py`, `tests/test_live.py`, `tests/fixtures/reference_outputs.json` only to add budget metadata, and the evidence document. Fill live targets only from actual successful discovery; preserve baseline identities.

**Interfaces:** Keep fixture case names and baseline outputs from Task 1. Add per-case fixed integer `max_chars` budgets for `compact` and `url`; initialize each to `ceil(measured_candidate_chars * 1.05)`, record the measured values, and commit the resulting literals. Tests never recompute their own ceiling from actual output.

- [x] **Step 1: Add semantic size tests** named `test_reference_output_budgets` and `test_long_toc_compact_is_smaller`. For every case assert the fixed ceiling, required title/content fields, and expected reference identities; for the 301-row long-path TOC assert `len(compact) < len(url_output)` and equal addressed-node sets. Exercise existing 500-line cap behavior separately with more than 500 nodes; compact formatting must not bypass it.
- [x] **Step 2: Verify the budget check can fail.** Temporarily lower one literal ceiling below its measured output; run `.\.venv\Scripts\python.exe -m pytest tests/test_reference_sizes.py -q` and observe that exact budget failure. Restore the correct literal, rerun, and expect all tests to pass. Do not reduce content or shorten fixture paths to obtain a pass.
- [x] **Step 3: Run fixed-target live measurements** with `.\.venv\Scripts\python.exe -m pytest -m live -q -s`. Read/list/TOC targets must match baseline IDs; record candidate compact and URL sizes. For live search, compare the returned identity set with baseline and flag upstream drift before attributing a size difference to the implementation. Record any fallback URL use and keep per-host throttling. No invented ratio, timing claim, or successful qualification when the relevant request failed.
- [x] **Step 4: Run final offline verification serially:** `.\.venv\Scripts\python.exe -m pytest -q --cov=siemens_docs_mcp.catalog --cov=siemens_docs_mcp.tools --cov=siemens_docs_mcp.rendering --cov=siemens_docs_mcp.server --cov-report=term-missing`, then `.\.venv\Scripts\ruff.exe check .`. Expect no failures/diagnostics. Review coverage of materially changed branches, aiming for at least 80%; do not add trivial tests just to raise unrelated coverage.
- [x] **Step 5: Complete the evidence document.** Record baseline and candidate commit IDs, fixture counts/sizes, fixed live targets, exact commands/results, schema/default changes, the independent stage A checkpoint, and any remaining live gaps. Distinguish attempted from successful measurements. Update plan progress only from observed results.
- [x] **Step 6: Review the whole diff against the spec.** Confirm converter/CLI architecture, dependencies, four-tool surface, pagination, and unrelated files were preserved. Seek independent review of the implemented branch before release. Review fixes receive their own relevant checks and conventional commits. No push, PR creation, merge, or release is authorized by this plan.
- [x] **Step 7: Commit qualification changes** with `test: qualify compact reference output budgets`. Report offline and live evidence separately. If live hosts remain unreachable, report offline completion and the outstanding live qualification rather than claiming the milestone fully qualified.

## Handoff and recovery

All five tasks are implemented and independently task-reviewed. Whole-branch independent review of `f774c294c77cc84f20ed436a552b991350f11bc3..bb9ef389da1e04ca98aea20c84c7ceb58e4f0c6a` found no Critical or Important issues and one minor stale-handoff documentation finding, addressed here. This documentation correction still requires scoped review. Stage A's refactor commit can stand independently; stage B is recoverable through explicit URL output and, if necessary, reverting the feature commits in dependency order while retaining the behavior-preserving extraction. Do not reset unrelated work or rewrite published history. No push, PR creation, merge, or release is authorized by this plan.
