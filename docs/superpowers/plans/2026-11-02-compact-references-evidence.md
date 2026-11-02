# Compact references qualification evidence

## Task 1: URL baseline, 2026-11-02

Starting commit: `f774c294c77cc84f20ed436a552b991350f11bc3` on
`refactor/compact-references`. Production source is unchanged in Task 1.
All sizes below are Python `len(output)` character counts, not measured tokens.

### Offline fixtures

The reviewed, literal baseline strings are in
[`tests/fixtures/reference_outputs.json`](../../../tests/fixtures/reference_outputs.json).
The eight cases use the shared catalog and cover both configured hosts.

| Case | URL characters |
| --- | ---: |
| tia_search | 213 |
| tia_list | 381 |
| tia_read | 185 |
| tia_toc | 215 |
| iox_search | 227 |
| iox_list | 233 |
| iox_read | 171 |
| iox_toc | 354 |

Review confirmed publication/topic titles, metadata, breadcrumbs, excerpts,
ordering, and provenance. Search fixtures deliberately show total counts larger
than the returned count; existing pagination and cap tests remain in place.
The duplicated body headings in the small read fixtures are existing converter
behavior and are recorded verbatim. Every emitted small-case address is exercised
through both read and TOC operations. Missing publication roots/bodies are filled
only for the reference cases so existing error-path fixtures stay meaningful.

The separate `long-reference` map has root `long-root`, 300 children with canonical
IDs `long-topic-0` through `long-topic-299`, and distinct TOC aliases
`long-toc-0` through `long-toc-299`. At depth 1 it emits 301 rows and **77,868
characters**. Every child URL path is at least 160 characters. Tests resolve all
301 rows and compare the canonical topic identities; the publication root URL's
absent content ID is normalized to its TOC root. Repetitive full output is not
stored. This map does not replace the small `tia2` or `iox1` fixtures.

### Fixed live targets

The committed manifest is
[`tests/fixtures/reference_live_targets.json`](../../../tests/fixtures/reference_live_targets.json).
Discovery successfully read the first returned topic and its TOC on both hosts.
The TIA publication metadata was checked for Openness. Observed targets were
pinned manually using the file-edit tool; the tests never rewrite the manifest.

- TIA query: `TIA Portal Openness`.
  Publication: [TIA Portal Openness V20](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows).
  Topic: [Installing TIA Portal Openness](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/basics/installation/installing-tia-portal-openness).
  Canonical map/topic: `Rc0LxW522mLHDCX_sejL~A` / `HZ7f9jFVFVga52ac6WpeDA`.
- IOX query: `OPC UA`.
  Publication: [Industrial Information Hub V2.7](https://docs.industrial-operations-x.siemens.cloud/r/en-us/v2.7/industrial-information-hub).
  Topic: [Loading the OPC UA model via OPC UA server](https://docs.industrial-operations-x.siemens.cloud/r/en-us/v2.7/industrial-information-hub/manage-data/setting-up-opc-ua-models/loading-the-opc-ua-model-via-opc-ua-server).
  Canonical map/topic: `Li4yDQJF3SPIB5lKtTioBA` / `DtlGcMzx28Bz2Y_H4~x5TA`.

Each fixed-target host test starts with a new catalog and client at the normal
0.3-second minimum request interval. Tool order is search, publication TOC at
depth 1, pinned topic read at default offset/max_chars, then publication listing.
Locale is `en-US`; search uses default limit 10. Listing uses the exact pinned
publication title as `title_contains` and may include other versions. The TIA
title is `TIA Portal Openness: API for automation of engineering workflows`;
the IOX title is `Industrial Information Hub`.

HTTP attempts count `_send` calls during the tool call, including authentication
and retries. Identity extraction happens afterward and may fetch/cache TOCs to
resolve pretty URLs; these validation requests are excluded from the preceding
tool's count. Therefore the following TOC call is warm in this sequence. The page
body is fetched normally. This is size evidence, not a latency benchmark.

| Host | Tool | URL chars | HTTP attempts | Distinct identities |
| --- | --- | ---: | ---: | ---: |
| TIA | search_docs | 6828 | 3 | 10 |
| TIA | get_toc | 1092 | 0 | 7 |
| TIA | read_page | 1923 | 1 | 1 |
| TIA | list_publications | 403 | 0 | 2 |
| IOX | search_docs | 6377 | 3 | 10 |
| IOX | get_toc | 1446 | 0 | 12 |
| IOX | read_page | 705 | 1 | 1 |
| IOX | list_publications | 2492 | 0 | 14 |

Tests print the complete identity set for every measurement. The following SHA256
fingerprints preserve the baseline sets without duplicating hundreds of IDs.
First sort the distinct `(host, map_id, content_id or "")` triples into `identities`.
Algorithm: `sha256(json.dumps(identities, separators=(",", ":"),
ensure_ascii=True).encode()).hexdigest()`.
These are output-address identities only; inline page-body links are excluded.

| Host/tool | Identity-set SHA256 |
| --- | --- |
| TIA/search | `8f03d02f6037e83dedb93002085f2f9b63109837d549e80af321ecd01db65377` |
| TIA/TOC | `8bd9ab838c4a6d3f227e8c5fd5a97ae30f961ac619c24b4357668a36dfa9e4a2` |
| TIA/read | `9f876c2816f0d39145b19472e4728bc3b76c9e36df045ec3975f0221230434e7` |
| TIA/list | `8f901a524a58af3135b192a7484345ee2eea12143890da9cd68c0cea9092ce85` |
| IOX/search | `1819ac7fa4107d41314e7120668c3bba7ab4973322a6b2b3e1584c7a5b545b71` |
| IOX/TOC | `80ac1c90cebd40be45dfb69763b56e42259915c0689a7f1b88df9d98606dc9b0` |
| IOX/read | `7c27cc5669e41f8849356a85743a182ff0723ce4bf2573b0898e1b5a307de21c` |
| IOX/list | `7cb079950d987e194d98a64368199a8621e5e593cbc170f809d4fe4121ea3ff6` |

The fixed topic/publication operations never substitute a fresh search result.
Search ranking and publication inventories remain upstream snapshots even with
fixed queries. Their identity fingerprints should be compared before interpreting
later size changes. No host availability gap remained in this baseline run.

### Verification

- Fixture TDD RED: `.\.venv\Scripts\python.exe -m pytest tests/test_reference_sizes.py -q`:
  2 expected failures, missing configurable
  `map_id` and missing `get_content_calls`; exit 1.
- Fixture GREEN with the same command: 2 passed; exit 0.
- `.\.venv\Scripts\python.exe -m pytest tests/test_reference_sizes.py tests/test_tools.py tests/test_server.py tests/test_cli.py -q`:
  60 passed in 3.21s; exit 0.
- `.\.venv\Scripts\python.exe -m pytest -q`: 124 passed, 4 live tests deselected,
  in 4.02s; exit 0.
- `.\.venv\Scripts\python.exe -m pytest -m live -q -s`: 4 passed, 124 deselected,
  in 23.89s; exit 0.
- After stronger fixed-target identity assertions,
  `.\.venv\Scripts\python.exe -m pytest -m live -q -s -k fixed_target_measurements`:
  2 passed, 126 deselected in 15.68s; exit 0. Sizes above are from this final run.
- `.\.venv\Scripts\ruff.exe check tests/conftest.py tests/test_reference_sizes.py tests/test_live.py tests/test_tools.py`:
  all checks passed; exit 0.

The initial live discovery run obtained both targets but failed in test cleanup
because `FluidtopicsClient` exposes a context manager rather than `close()`.
The harness was corrected to use its existing context manager. An initial
long-TOC assertion also expected the publication URL to resolve directly to the
root content ID; it now uses the existing publication-root semantics. Final test
and Ruff runs emitted no warnings. Git reports normal LF-to-CRLF working-copy
conversion warnings; these are separate from the test output.

## Task 5: Candidate qualification, 2026-11-02

Implementation baseline: `f774c294c77cc84f20ed436a552b991350f11bc3`.
The Task 1 fixture/live capture is retained from `67fb431`.
Independent behavior-preserving stage A checkpoint:
`802c7693c47ffcd070c46741de5692a70540db7f`.
Measured stage B candidate and qualification parent:
`a83b3e95cd0a17d7a7f81a923217ece69d974a1a`.
Task 5 adds tests, literal measurement metadata, and evidence; production source
is identical to that candidate. All sizes are Python character counts, not tokens.

### Literal fixture ceilings and semantic checks

Each ceiling was calculated once as `ceil(measured_candidate_chars * 1.05)` and
stored as an integer in `max_chars`; tests read the fixed literal and never
derive a ceiling from their actual output. `measured_candidate_chars` records
the corresponding observations. Existing case names, `output` strings, and
`chars` remain byte-for-byte unchanged against Task 1.

| Case | Compact chars | URL chars | Compact ceiling | URL ceiling |
| --- | ---: | ---: | ---: | ---: |
| tia_search | 166 | 213 | 175 | 224 |
| tia_list | 218 | 381 | 229 | 401 |
| tia_read | 138 | 185 | 145 | 195 |
| tia_toc | 101 | 215 | 107 | 226 |
| iox_search | 168 | 227 | 177 | 239 |
| iox_list | 111 | 233 | 117 | 245 |
| iox_read | 112 | 171 | 118 | 180 |
| iox_toc | 115 | 354 | 121 | 372 |

`test_reference_output_budgets` checks both formats for all eight cases. It
asserts the fixed ceiling, exact ordered reference identities and host, address
count, and complete equality with golden content after replacing only the
tool-generated address fields. This retains titles, metadata, excerpts,
breadcrumbs, provenance, page body, and ordering independently of size.
The existing round-trip tests additionally read every emitted small-case target.

The unchanged 301-row long-path fixture measures **16,333 compact characters**
versus **77,868 URL characters**. `test_long_toc_compact_is_smaller` requires
smaller compact output, identical titles/indentation, and equality of all 301
effective addressed-node identities. Publication root URLs are normalized to
their actual TOC root. A separate synthetic TOC contains 601 nodes; both formats
emit exactly the first 500 addressed rows plus the original truncation message.
Its 500 ordered canonical identities are checked. The long fixture's paths and
content were not shortened to pass a budget.

### Failure demonstration and offline verification

Command: `.\.venv\Scripts\python.exe -m pytest tests/test_reference_sizes.py -q`.
Temporarily changing only `tia_search.max_chars.compact` from 175 to 165 gave:

```text
FAILED tests/test_reference_sizes.py::test_reference_output_budgets[compact]
AssertionError: ('tia_search', 'compact', 166)
assert 166 <= 165
1 failed, 13 passed in 2.11s
exit 1
```

Restoring the literal 175 and running the same command gave
`14 passed in 1.73s`, exit 0. No output or fixture identity was changed for this
demonstration. Before that demonstration, an initial cap-test fixture used an
ID-looking pretty path (`/r/big/t0`) and incorrectly expected it to resolve as a
pretty URL; the fixture was corrected to use a coherent nested pretty path.
That harness failure was `1 failed, 13 passed in 2.49s`; the corrected focused
run was `14 passed in 1.86s`. No production fix was needed.

Final checks ran serially after the last Python test edit:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=siemens_docs_mcp.catalog --cov=siemens_docs_mcp.tools --cov=siemens_docs_mcp.rendering --cov=siemens_docs_mcp.server --cov-report=term-missing
.\.venv\Scripts\ruff.exe check .
```

The coverage command returned `291 passed, 4 deselected in 6.26s`, exit 0:

| Module | Statements | Missing | Statement coverage |
| --- | ---: | ---: | ---: |
| catalog.py | 225 | 0 | 100% |
| rendering.py | 35 | 0 | 100% |
| server.py | 70 | 4 | 94% |
| tools.py | 118 | 0 | 100% |
| Total | 448 | 4 | 99% |

Uncovered server lines are 144–146 and 150 (process startup). These percentages
are statement coverage, not a separately measured branch-coverage percentage.
The existing parser, fallback, before-fetch rejection, schema, round-trip,
pagination, CLI, and converter regressions are included in the passing suite;
no tests were added merely to raise unrelated coverage. Ruff returned
`All checks passed!`, exit 0. Final test/lint output contained no warnings.
`git diff --check` also returned exit 0 before the documentation update.

### Fixed-target live candidate measurements

Command: `.\.venv\Scripts\python.exe -m pytest -m live -q -s`.
Final result: `4 passed, 291 deselected in 24.98s`, exit 0. An earlier run before
adding effective-node comparison also passed (`4 passed, 291 deselected in
25.04s`); its raw TIA search identity mismatch prompted the investigation below.
Both hosts were reachable. All 16 fixed-target tool/format calls succeeded.
The pinned manifest and the map/topic targets listed in Task 1 are unchanged.
Each pinned read verifies its exact canonical map/topic pair; TOC/list verify the
baseline map and the complete output identity fingerprint.

| Host | Tool | Baseline URL chars | Candidate URL chars | Candidate compact chars | URL HTTP attempts | Compact HTTP attempts |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| TIA | search_docs | 6828 | 6828 | 5739 | 3 | 1 |
| TIA | get_toc | 1092 | 1092 | 574 | 0 | 0 |
| TIA | read_page | 1923 | 1923 | 1815 | 1 | 1 |
| TIA | list_publications | 403 | 403 | 243 | 0 | 0 |
| IOX | search_docs | 6377 | 6377 | 5227 | 3 | 1 |
| IOX | get_toc | 1446 | 1446 | 802 | 0 | 0 |
| IOX | read_page | 705 | 705 | 584 | 1 | 1 |
| IOX | list_publications | 2492 | 2492 | 1539 | 0 | 0 |

The fixed-target test uses a fresh catalog/client per host and the normal
0.3-second per-host minimum interval. Tool order is search, pinned publication
TOC (depth 1), pinned topic read (default offset/max_chars), then exact-title
publication listing; each tool runs URL first, compact second. Search uses the
fixed query, `en-US`, and default limit 10. Listing uses the same exact titles as
Task 1. Only the first URL search has cold metadata; subsequent calls may reuse
metadata/TOC caches. Each `_send` attempt is counted before identity validation;
validation TOC requests and cache warming are excluded from that call's count.
Effective-node normalization is validation-only and does not add production
search requests. The discovery tests are separate from these pinned operations.
These are size measurements, not a latency benchmark.

Every compact measurement had **zero fallback reader URLs** and **zero
unavailable-reference markers**. Existing offline fallback tests cover malformed
upstream hits; this live snapshot does not qualify a naturally occurring fallback
case. Page-body URLs are outside the address-field counts and remain unchanged.

### Search identity comparison and root equivalence

All candidate URL identity fingerprints match the eight baseline fingerprints
recorded above. IOX search compact and URL fingerprints are both
`1819ac7fa4107d41314e7120668c3bba7ab4973322a6b2b3e1584c7a5b545b71`.
TIA search URL retains baseline fingerprint
`8f03d02f6037e83dedb93002085f2f9b63109837d549e80af321ecd01db65377`;
compact has raw fingerprint
`67538148d395ea743b25c5c01d9eb0e92795fb57298e432a0c8430ba1456e12f`.
Both have 10 distinct addresses. The only raw-set difference is:

```text
URL:     (docs.tia.siemens.cloud, 5_QWRtE02wdb1Wg3xHZ4Nw, "")
compact: (docs.tia.siemens.cloud, 5_QWRtE02wdb1Wg3xHZ4Nw, eIJ3mivEAF2n2ISrMGgzKg)
```

A separate live check through `Catalog.toc` confirmed that this publication's
root content ID is `eIJ3mivEAF2n2ISrMGgzKg`. Reading `tia:5_QWRtE02wdb1Wg3xHZ4Nw`
and `tia:5_QWRtE02wdb1Wg3xHZ4Nw/eIJ3mivEAF2n2ISrMGgzKg` returned byte-identical
705-character outputs. Its diagnostic output was:

```text
root_content_id eIJ3mivEAF2n2ISrMGgzKg matches_compact True
publication_and_root_reads_equal True chars 705 705
exit 0
```

The final harness retains and prints the raw fingerprint difference separately
from `effective_node_match: true`, which resolves publication-only addresses to
their actual roots. All eight paired comparisons have effective-node equality.
The compact TIA search difference is therefore a verified publication/root
representation difference; **no upstream identity drift is established**.
The original baseline did not record raw API hit IDs, so it cannot establish
whether upstream identity fields themselves changed. This limits that historical
claim without invalidating the observed same-node candidate comparison. No
reduction ratio or token/timing claim is made from these measurements.

### Scope and remaining review

The delivered MCP schema has exactly four tools; each exposes optional
`reference_format` with enum `compact`, `url` and default `compact`. Required
`url` names and prior positional arguments remain. Only generated address fields
change spelling; explicit URL mode preserves all eight golden outputs.
The independent stage A extraction remains recoverable at its own commit.
Git comparison confirms CLI, converter, and dependencies unchanged from the
implementation baseline, and the live target manifest unchanged from Task 1.
Task 5 changes no production code or unrelated files. Existing cap/pagination
and URL-based export tests pass. The implementer self-reviewed the qualification
diff; controller whole-branch independent review remains pending. No push, PR,
merge, deployment, or release was performed.
