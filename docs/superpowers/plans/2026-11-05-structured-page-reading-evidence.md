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

## Fixture sizes (Task 7, offline)

`tests/fixtures/html/openness_page.html` read as `tia2-p1` in the test catalog. Ceilings in
`tests/test_reading_sizes.py` are these values +5%.

| Call | chars |
| --- | ---: |
| full, compact | 1039 |
| full, url | 1115 |
| `mode="outline"` | 405 |
| `section="Program code"` | 536 |
| `mode="code"` | 536 |
| `mode="code", section="Program code"` | 536 |

The fixture's "Program code" sections hold only code, so section and code views coincide here.

## Live "after" measurements (Task 8, 2026-11-05)

Same conditions as the "before" run (`test_reading_measurements`, one catalog/client per host,
`min_interval=0.3`, cold catalog at each host's first page). `—` = no "Program code" heading (the
tool returned its no-match or no-headings error, listing the page's sections).

| Page | full compact before → after | full url before → after | outline | section "Program code" | code |
| --- | ---: | ---: | ---: | ---: | ---: |
| tia_installing_openness | 1815 → 1815 | 1923 → 1923 | 471 | — | 313 |
| tia_compiling_a_project | 3988 → 3930 | 4129 → 4129 | 525 | 2365 | 1977 |
| tia_export_import_sub_modules | 18535 → 17834 | 18669 → 18113 | 750 | — | 10873 |
| iox_loading_opc_ua_model | 584 → 584 | 705 → 705 | 299 | — | 267 (no-code note) |
| iox_browse_hierarchy_members | 1455 → 1091 | 1606 → 1242 | 337 | — | 305 |

Observations:

- Compact topic links save 58 and 145 characters on the two TIA pages with topic links; dropping
  image/attachment URLs saves 556 (TIA sub modules, url mode) and 364 (IIH hierarchy page, both formats).
- An outline costs 300-750 characters; on the 18k-character sub modules page it is 4% of the full read.
  Code view on "Compiling a project" is 50% of the full read; `section="Program code"` is 60%.
- Every compact body link on these pages (6 in total) read back successfully with `read_page`.
- Paging every page at `max_chars=1000` (up to 21 chunks) produced no chunk with an unbalanced code fence.
- Page bodies differ only where links or images occur; the headers and text are unchanged.

## Mid-branch adversarial review fixes (after Task 4)

- Malformed body hrefs (e.g. `http://[IP address of the CPU]/`) no longer crash `read_page`; they stay unchanged.
- Chrome removed between two text nodes no longer splits a line in note/code tables (`soup.smooth()`).
- Per-block post-processing trims only blank lines; leading spaces are stripped once at the body start, as before.

Live byte-identity re-run after these fixes: 120/120 TIA and 40/40 IIH pages identical to the base converter.

## Final review fixes (after Task 8)

- Chunking dead ends fixed: a code block with an over-long first line, and a last block or last code
  line at exactly the budget, can now be read; "start the next chunk here" is decided by trying the
  same line split with a full budget, so it can no longer disagree with the splitter.
- Continuation lines repeat `reference_format="url"`; only same-host body links are compacted.
- Reviewer fuzz re-run on the fixed splitter: 300 random block lists, hint traversal with no errors,
  no over-budget chunk, no content mismatch, no unbalanced fence; 4000 max_chars-switching cases
  with no loss; all exact-budget edge cases readable.
