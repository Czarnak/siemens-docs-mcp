# Structured page reading: evidence

Plan: [Structured page reading](2026-11-05-structured-page-reading.md).
Spec: [Design](../specs/2026-11-05-structured-page-reading-design.md).

All sizes are characters of complete `read_page` output (header included). No token counts.

## Base commit

Converter before any change: `5e56237` (identical `converter.py`/`content.py` to `1fb1f25`, main at PR #6).
Offline goldens of that converter: `tests/fixtures/converter_golden.json` (18 cases).

## Live "before" measurements (2026-11-05)

Conditions: `tests/test_live.py::test_reading_measurements`, one catalog/client per host,
`min_interval=0.3`, cold catalog at the first page of each host, warm afterwards.
Pinned pages: `tests/fixtures/reading_live_targets.json`.

| Page | full, compact | full, url |
| --- | ---: | ---: |
| tia_installing_openness | 1815 | 1923 |
| tia_compiling_a_project | 3988 | 4129 |
| tia_export_import_sub_modules | 18535 | 18669 |
| iox_loading_opc_ua_model | 584 | 705 |
| iox_browse_hierarchy_members | 1455 | 1606 |

Before this milestone the two formats differ only in the `> Source:` header line; body links are
identical.

Note: the plan named "Compiling technology object" as a pinned page, but that topic is not in the
pinned Openness V20 publication. "Compiling a project" (several "Program code" sections) replaces it.

## Parse-once byte identity (Task 3, live, 2026-11-05)

Old path: base-commit `content._clean_html` + `converter.html_to_markdown` (string, parsed twice).
New path: `content.fetch_soup` + block-based `html_to_markdown` (parsed once). Both fed the same raw
response per page. Sample: `random.seed(7)`, 120 Openness V20 pages and 40 IIH V2.7 pages (same
seed and sizes as the design's link sample), `min_interval=0.3`.

| Host | Pages | Identical |
| --- | ---: | ---: |
| docs.tia.siemens.cloud | 120 | 120 |
| docs.industrial-operations-x.siemens.cloud | 40 | 40 |

Offline: all 18 golden cases are identical through both the string path and the soup path.
