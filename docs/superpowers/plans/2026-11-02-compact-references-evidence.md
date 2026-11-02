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
