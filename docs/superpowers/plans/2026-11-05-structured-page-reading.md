# Structured Page Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `read_page` return a heading outline, selected sections, or only code, cut every chunk at block boundaries, and emit compact references for topic links in page bodies, after a separately verified behavior-preserving converter refactor.

**Architecture:** The converter returns a flat list of `Block`s rendered by today's functions; `html_to_markdown` joins them. A new pure module `reading.py` builds sections, outline rows, code views and chunks over that list. `tools.read_page` validates and coordinates; `rendering.py` formats; `catalog.py` owns body-link classification.

**Tech Stack:** Python >=3.11, BeautifulSoup, markdownify, MCP SDK, pytest, Ruff. No dependency changes.

**Spec:** [Structured page reading design](../specs/2026-11-05-structured-page-reading-design.md), approved 2026-11-05.

## Global Constraints

- Keep the four tool names and existing `read_page` parameters (`url`, `offset`, `max_chars`, `reference_format`) with their bounds: `max_chars` 1000-100000, `offset >= 0`.
- New `read_page` parameters: `section: int | str | None = None`, `mode: "full" | "outline" | "code" = "full"`. `""` counts as unset for both.
- `mode="outline"` with `section` or `offset > 0` is an error. Unknown `mode` is an error naming the allowed values. Argument errors cause zero client requests.
- A default call (no new parameters) changes only by the link rule and block-boundary cuts.
- Exporter (CLI) Markdown output must not change at all.
- Link rule: allowed host + `/r/<mapId>[/<contentId>]` → compact reference in compact mode, unchanged in url mode; allowed-host `/viewer/attachment/…` and `/api/khub/maps/…/resources/…` → label only in both modes; everything else unchanged; images → alt text only in both modes.
- Link rewriting performs no network request.
- No cut inside a code fence, table row or line, except a single line with no space longer than the budget (cut at `max_chars`).
- `offset` is a character position in the view text; the continuation line is `[truncated — call again with offset=N]`, preceded by `section=…` and `mode=…` arguments when those are set.
- No new tool, no link footer, no code-language guessing, no change to search/TOC/list output.
- Record characters, not tokens. Live unavailability is an evidence gap, never an offline success claim.
- Commit messages: short one-liners.

### Clarifications to the spec made while planning

1. **`compact_link` checks the map id against the already-loaded publication list** (no fetch; if that host's list isn't loaded, the link stays unchanged). The spec said "no check that the map exists"; without the check a two-segment pretty URL (`/r/foo/bar`) would be rewritten as a bogus reference. `read_page` has always loaded its own host's list, so same-host links (the 84% case) are still rewritten.
2. **Links with a query or fragment stay unchanged** (e.g. `…/r/<map>/<topic>?section=`), so in-page anchors are never lost.
3. **Resuming inside an oversized block:** go back to the start of the line containing `offset` only if that line fits within `max_chars`; otherwise resume exactly at `offset`. Without this, a long line split at a space would loop back to its start forever.
4. **A block larger than `max_chars` fills the remaining budget of the current chunk** instead of always starting a new chunk. Without this, a page title followed by one huge paragraph would return an 8-character first chunk.
5. **`read_page` treats a page that renders zero blocks as empty** (the `*No content available.*` line). The exporter's `html_to_markdown` keeps its exact legacy output for that case.

## Review Focus

1. An agent changes `max_chars` between calls and passes an offset from an earlier hint: it must resume at the right block without loss or duplication (Task 6).
2. `section="Program code: Compiling"` (a partial heading after the colon) must not silently match; the error must list the headings (Task 5).
3. A code block in the lead (before any heading) must appear in code view without a heading line (Task 5).
4. A topic link with `?section=` or `#anchor` must stay unchanged (Task 4).
5. Headings with markup (`## **Properties** of Safety telegrams`) must match `"properties of safety telegrams"` (Task 5).

---

## File map

| File | Change | Task |
| --- | --- | --- |
| `tests/fixtures/html/openness_page.html` | New Openness-like page fixture | 1 |
| `tests/fixtures/converter_golden.json`, `tests/test_converter_golden.py` | Recorded legacy converter output | 1 |
| `tests/fixtures/reading_live_targets.json`, `tests/test_live.py` | Pinned live pages, before/after measurements | 1, 8 |
| `docs/superpowers/plans/2026-11-05-structured-page-reading-evidence.md` | Measurements and comparison results | 1, 3, 8 |
| `siemens_docs_mcp/converter.py`, `tests/test_converter.py` | `Block`, `html_to_blocks`, hooks | 2, 4 |
| `siemens_docs_mcp/content.py`, `siemens_docs_mcp/cli.py`, `siemens_docs_mcp/tools.py` | Parse once | 3 |
| `siemens_docs_mcp/catalog.py`, `tests/test_catalog.py` | `compact_link`, `is_attachment_link` | 4 |
| `siemens_docs_mcp/reading.py`, `tests/test_reading.py` | Sections, outline, code view, chunking | 5, 6 |
| `siemens_docs_mcp/rendering.py`, `tests/test_rendering.py` | Outline and continuation rendering | 7 |
| `siemens_docs_mcp/tools.py`, `siemens_docs_mcp/server.py`, `tests/test_tools.py`, `tests/test_server.py`, `tests/test_reading_sizes.py` | Wiring, schema, size ceilings | 4, 7 |
| `README.md`, roadmap | Docs and status | 7, 8 |

Run tasks in order; they share interfaces. Commands: `uv run pytest -q` (offline suite), `uv run ruff check .`, live: `uv run pytest -m live -s tests/test_live.py -k reading`.

---

### Task 1: Baselines before any change

Tests and fixtures only; no production code.

**Files:**
- Create: `tests/fixtures/html/openness_page.html`, `tests/fixtures/converter_golden.json`, `tests/test_converter_golden.py`, `tests/fixtures/reading_live_targets.json`, evidence doc
- Modify: `tests/test_live.py`

**Interfaces:**
- Produces: fixture `openness_page.html` used by Tasks 2, 4, 7. Content, as Siemens markup:
  - a lead `<p>` with a topic link `https://docs.tia.siemens.cloud/r/tia1/topic-a`
  - `<p class="Blocktitle">Requirement</p>` + a paragraph with an external link `https://support.industry.siemens.com/cs/us/en/view/109760816`
  - `<p class="Blocktitle">Program code: Compiling a technology object</p>` + a `<table class="table_sourcecode">` with three `p_table_l_code` lines
  - `<p class="Blocktitle">Program code: Compiling the technology object group</p>` + a code table + `<a href="https://docs.tia.siemens.cloud/viewer/attachment/tia1/res-1"><img alt="" src="https://docs.tia.siemens.cloud/api/khub/maps/tia1/resources/res-1/content?v=1"></a>`
  - `<p class="BlocktitleFirst">Compile results</p>` + a two-row regular table + a paragraph linking `https://docs.tia.siemens.cloud/r/tia1/topic-b?section=`
  - all wrapped in two nested `<div>`s
- Produces: `converter_golden.json` = `{case: {"html": str, "title": str, "markdown": str}}`. Cases: both existing HTML fixtures and `openness_page.html` (after `_clean_html`), and every inline HTML snippet in `tests/test_converter.py`. Add snippets for: h1-h6 including an empty `<h2></h2>`, a div holding two identical child divs (duplicate removal), a `<ul>` with nested `<ol>` and a safety table inside an item, a safety table with a "Note" label, `<pre>`, a data-URI image, an image with a real `src`, a `<dl>` containing a link, and a tags-only `<div><span></span></div>`.
- Produces: `reading_live_targets.json` = `{"pages": [{"label": str, "url": str}]}` with the two existing `topic_url`s and, found by search on the TIA host in TIA Portal Openness V20, "Compiling technology object" and "Export/Import of sub modules", plus one IIH page that contains an image (pin the URL you found).

- [ ] **Step 1: Record the base commit** (`git rev-parse HEAD`) in the evidence doc. Task 3 compares against it.
- [ ] **Step 2: Write `tests/test_converter_golden.py`**

```python
@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_converter_matches_recorded_output(case):
    entry = GOLDEN[case]
    assert html_to_markdown(entry["html"], entry["title"]) == entry["markdown"]
```

- [ ] **Step 3: Generate `converter_golden.json` with the current `html_to_markdown`** using a one-off script outside the repository. Read the generated Markdown for each case and confirm it is what today's converter is meant to produce.
- [ ] **Step 4: Run** `uv run pytest -q tests/test_converter_golden.py`. Expected: all pass.
- [ ] **Step 5: Add live test `test_reading_measurements`** (marked `live`). For each pinned page, call `tools.read_page(cat, url, reference_format=fmt)` for `fmt in ("compact", "url")`, using one catalog/client per host at `DEFAULT_MIN_INTERVAL`, and print `MEASUREMENT {"label", "mode": "full", "format", "chars"}` as JSON. Task 8 extends this test.
- [ ] **Step 6: Run it live** and record the "before" numbers in the evidence doc, with date and throttle. If the hosts are unreachable, record the gap.
- [ ] **Step 7: Full suite + ruff green, commit:** `test: record converter and reading baselines`

### Task 2: Converter emits blocks (no behavior change)

**Files:** Modify `siemens_docs_mcp/converter.py`; test `tests/test_converter.py`.

**Interfaces:**
- Produces:
  ```python
  BlockKind = Literal["heading", "paragraph", "code", "table", "list", "quote", "other"]
  @dataclass(frozen=True)
  class Block:
      kind: BlockKind
      text: str
      level: int = 0
  LinkRewrite = Callable[[str], str | None]
  def html_to_blocks(source: BeautifulSoup | str, *, link: LinkRewrite | None = None, images: bool = True) -> list[Block]
  def html_to_markdown(source: BeautifulSoup | str, title: str, *, link: LinkRewrite | None = None, images: bool = True) -> str
  ```
  `link` and `images` are accepted but have no effect until Task 4.
- Kind mapping: `h1`-`h6` → heading, level N; `Blocktitle`/`BlocktitleFirst` paragraph → heading, level 2; code-class paragraphs, `pre`, `table_sourcecode` → code; regular table → table; safety table, admonition → quote; `ul`/`ol` → list; plain paragraph and standalone image → paragraph; markdownify fallback → other.

- [ ] **Step 1: Write failing tests**

```python
def test_blocks_kinds_and_levels():
    html = ('<div><p class="Blocktitle">Requirement</p><p>Text</p><h3>Deep</h3>'
            '<table class="table_sourcecode"><tr><td><p class="p_table_l_code">x();</p></td></tr></table>'
            '<table class="safety"><tr><td>Note</td><td>Careful</td></tr></table>'
            '<ul><li>a</li></ul><table><tr><td>h</td></tr><tr><td>v</td></tr></table></div>')
    assert [(b.kind, b.level) for b in html_to_blocks(html)] == [
        ("heading", 2), ("paragraph", 0), ("heading", 3), ("code", 0),
        ("quote", 0), ("list", 0), ("table", 0)]

def test_blocks_open_nested_divs_and_drop_adjacent_duplicates():
    blocks = html_to_blocks("<div><div><p>A</p><p>B</p></div><div><p>A</p><p>B</p></div></div>")
    assert [b.text for b in blocks] == ["A", "B"]

def test_blocks_empty_source():
    assert html_to_blocks("") == [] and html_to_blocks("  \n") == []

def test_html_to_markdown_is_blocks_joined():
    html = FIX.joinpath("openness_page.html").read_text("utf-8")
    blocks = html_to_blocks(_clean_html(html))
    assert html_to_markdown(_clean_html(html), "T") == "# T\n\n" + "\n\n".join(b.text for b in blocks) + "\n"
```

- [ ] **Step 2: Run them**, expect FAIL (`ImportError: html_to_blocks`).
- [ ] **Step 3: Implement.** Turn `_render_block` into a generator yielding `Block`s. Containers (`div` and unknown tags with block children) yield their children's blocks. Admonitions, lists and tables stay single blocks rendered by today's functions. Thread one frozen `_Options(link, images)` value through the render functions as a parameter rather than module state, so Task 4 can use it. Duplicate removal inside a `div` compares each child's whole block sequence with the previous child's, which is today's rule. Apply `_post_process` to each block's text and drop blocks left empty. `html_to_markdown` keeps the legacy strings: for empty source, `"# {title}\n\n*No content available.*\n"`; otherwise `f"# {title}\n\n{body}\n"`, where `body` is the blocks joined with `"\n\n"` (empty string when there are none).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass, including every golden case unchanged.
- [ ] **Step 5: Commit:** `refactor: emit converter blocks`

### Task 3: Parse the page HTML once

**Files:** Modify `siemens_docs_mcp/content.py`, `cli.py`, `tools.py`; test `tests/test_converter.py`, `tests/test_cli.py`.

**Interfaces:**
- Produces: `fetch_soup(client: FluidtopicsClient, map_id: str, content_id: str) -> BeautifulSoup | None` (None when the raw content is empty or whitespace). It cleans chrome in place via `_clean_soup(soup: BeautifulSoup) -> None`, and `_clean_html(html) -> str` becomes `str` of a cleaned soup. `fetch_html` returns `str(fetch_soup(...))`, or `""` for None.
- Consumes: `html_to_markdown(source, title)` from Task 2.

- [ ] **Step 1: Write a failing test** that, for every golden case, cleaning a soup and converting it gives the same Markdown as the string path:

```python
@pytest.mark.parametrize("case", sorted(GOLDEN))
def test_soup_path_matches_string_path(case):
    entry = GOLDEN[case]
    soup = BeautifulSoup(entry["html"], "html.parser")
    _clean_soup(soup)
    assert html_to_markdown(soup, entry["title"]) == html_to_markdown(_clean_html(entry["html"]), entry["title"])
```

  Also add a CLI test showing that the export of one page writes the same Markdown as `html_to_markdown(_clean_html(raw), title)`.
- [ ] **Step 2: Run**, expect FAIL (`ImportError: _clean_soup`).
- [ ] **Step 3: Implement** `fetch_soup`/`_clean_soup`. Switch `read_page` and the CLI loop to `fetch_soup` → `html_to_markdown(soup or "", title)`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Live byte-identity check.** Run a script outside the repo. It loads the base-commit `converter.py` and `content.py` (`git show <base>:…`) as a separate module, picks the same seeded random sample as the design evidence (120 Openness V20 pages, 40 IIH V2.7 pages), and compares the old string path with the new soup path page by page. Record "N/N identical" or the differing pages in the evidence doc. Any difference blocks the next task until it is explained and either fixed or accepted by the user.
- [ ] **Step 6: Commit:** `refactor: parse page html once`

### Task 4: Compact body links and alt-only images

**Files:** Modify `converter.py`, `catalog.py`, `tools.py`, `server.py`; test `tests/test_converter.py`, `tests/test_catalog.py`, `tests/test_tools.py`.

**Interfaces:**
- Produces in `catalog.py`:
  - `Catalog.compact_link(url: str) -> str | None`. Returns a compact reference when all of these hold: scheme is http/https; host is allowed; query and fragment are empty; path is `/r/<a>` or `/r/<a>/<b>` with valid id segments; and `<a>` is a map id in that host's **already loaded, fresh** publication list (read the cache; never call `maps()`). Otherwise `None`.
  - `Catalog.is_attachment_link(url: str) -> bool`. True when the host is allowed and the path starts with `/viewer/attachment/` or matches `/api/khub/maps/<id>/resources/`.
- Produces in `tools.py`: `_body_link(catalog: Catalog, reference_format: ReferenceFormat) -> LinkRewrite`. Attachment → `None`; compact mode → `compact_link(href) or href`; url mode → `href`.
- Converter hooks: `link` returning a string replaces the href; returning `None` keeps only the label. With `images=False`, an image renders as its alt text, and an anchor whose label comes out empty renders nothing. The markdownify fallback applies the same hooks to a copy of the tag (rewrite or unwrap anchors, replace images) before calling markdownify.

- [ ] **Step 1: Write failing tests**

```python
# test_catalog.py
def test_compact_link_rewrites_known_map_without_fetching(catalog, fake_tia):
    catalog.maps(TIA_HOST)
    calls = fake_tia.list_maps_calls
    assert catalog.compact_link(f"https://{TIA_HOST}/r/tia1/topic-a") == "tia:tia1/topic-a"
    assert catalog.compact_link(f"https://{TIA_HOST}/r/tia1") == "tia:tia1"
    assert fake_tia.list_maps_calls == calls

@pytest.mark.parametrize("url", [
    f"https://{TIA_HOST}/r/tia1/topic-b?section=", f"https://{TIA_HOST}/r/tia1/topic-b#s1",
    f"https://{TIA_HOST}/r/en-us/v21/doc/chapter-1", f"https://{TIA_HOST}/r/unknown/x",
    "https://support.industry.siemens.com/cs/us/en/view/1", "/r/tia1/x",
])
def test_compact_link_leaves_others(catalog, url):
    catalog.maps(TIA_HOST)
    assert catalog.compact_link(url) is None

def test_compact_link_needs_loaded_maps(catalog, fake_iox):
    assert catalog.compact_link(f"https://{IOX_HOST}/r/iox1/iox1-p1") is None
    assert fake_iox.list_maps_calls == 0

def test_is_attachment_link(catalog):
    assert catalog.is_attachment_link(f"https://{TIA_HOST}/viewer/attachment/m/r")
    assert catalog.is_attachment_link(f"https://{TIA_HOST}/api/khub/maps/m/resources/r/content?v=1")
    assert not catalog.is_attachment_link(f"https://{TIA_HOST}/r/tia1/x")
    assert not catalog.is_attachment_link("https://example.com/viewer/attachment/m/r")

# test_converter.py
def test_link_hook_and_images_off():
    html = ('<p><a href="A">one</a> <a href="B">two</a> <a href="C"><img alt="" src="i.png"></a>'
            ' <img alt="Diagram" src="d.png"></p>')
    md = html_to_markdown(html, "T", link=lambda h: {"A": "tia:m/a", "B": None}.get(h, h), images=False)
    assert "[one](tia:m/a) two" in md and "Diagram" in md
    assert "i.png" not in md and "d.png" not in md and "](C)" not in md

def test_link_hook_reaches_markdownify_fallback():
    md = html_to_markdown('<dl><dt><a href="A">term</a></dt><dd>d</dd></dl>', "T", link=lambda h: "tia:m/a")
    assert "tia:m/a" in md and "(A)" not in md

# test_tools.py (module constant reused by Task 7)
OPENNESS_HTML = (Path(__file__).parent / "fixtures" / "html" / "openness_page.html").read_text("utf-8")

@pytest.mark.parametrize("reference_format", ["compact", "url"])
def test_read_page_body_links(catalog, fake_tia, reference_format):
    fake_tia.contents[("tia2", "tia2-p1")] = OPENNESS_HTML
    out = read_page(catalog, "tia:tia2/tia2-p1", reference_format=reference_format)
    topic = "tia:tia1/topic-a" if reference_format == "compact" else f"https://{TIA_HOST}/r/tia1/topic-a"
    assert f"]({topic})" in out
    assert f"https://{TIA_HOST}/r/tia1/topic-b?section=" in out
    assert "support.industry.siemens.com" in out
    assert "viewer/attachment" not in out and "api/khub" not in out
```

  Keep the existing `test_body_links_are_unchanged`: it uses a pretty URL, which stays unchanged.
- [ ] **Step 2: Run**, expect FAIL.
- [ ] **Step 3: Implement** the two catalog methods, the converter hooks, and `_body_link`. `read_page` passes `link=_body_link(...)` and `images=False`; the CLI passes nothing. In `server.py`, replace the sentence "Page-body links are unchanged." with: "Links to other topics in a page body follow reference_format; images keep only their alt text." Put it in the `read_page` description only, and drop it from the shared `_REFERENCE_DOC`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass, golden cases unchanged (no hooks there).
- [ ] **Step 5: Commit:** `feat: compact topic links in page bodies`

### Task 5: Sections, outline rows and code view (pure)

**Files:** Create `siemens_docs_mcp/reading.py`, `tests/test_reading.py`.

**Interfaces:**
- Consumes: `Block` from Task 2.
- Produces:
  ```python
  ReadMode = Literal["full", "outline", "code"]
  @dataclass(frozen=True)
  class Section:
      number: int                 # 0 = lead
      heading: Block | None       # None for the lead
      blocks: tuple[Block, ...]   # heading first, nested sections included
  @dataclass(frozen=True)
  class OutlineRow:
      number: int
      label: str                  # heading text with # markers, "(before first heading)" or "(whole page)"
      chars: int
      code_blocks: int
  def view_text(blocks: Sequence[Block]) -> str            # "\n\n".join(texts) + "\n"; "" for no blocks
  def split_sections(blocks: Sequence[Block]) -> list[Section]
  def heading_match_text(block: Block) -> str
  def select_sections(blocks: Sequence[Block], section: int | str) -> list[Block]
  def code_view(blocks: Sequence[Block]) -> list[Block]
  def outline_rows(blocks: Sequence[Block]) -> list[OutlineRow]
  ```
- Rules (spec "Sections", "Outline output", "Full, section and code views"):
  - The lead is listed only if non-empty.
  - Headings are numbered from 1 in document order. A section ends at the next heading whose level is less than or equal to its own.
  - Match text strips `**`, `*`, backticks and `[text](url)` → `text`, removes the leading `#`s, and collapses whitespace. A section matches when its match text, compared case-insensitively, equals `section`, or starts with `section + ":"`.
  - When matches overlap, keep only the outer section; results stay in document order.
  - `select_sections` raises `ValueError` when there are no headings ("This page has no headings; read it without section.") or no match. The no-match message lists close matches first (`difflib.get_close_matches`), then every `number. heading` line.
  - `code_view` emits the last heading seen before each run of code blocks (nothing for code in the lead) followed by those code blocks.
  - `OutlineRow.chars = len(view_text(section.blocks))`.

- [ ] **Step 1: Write failing tests.** Build blocks with small helpers `h(level, text)`, `p(text)` and `c(text)`.

```python
PAGE = [p("lead"), h(2, "Requirement"), p("req"), h(2, "Program code: Compile one"), c("```\na();\n```"),
        h(3, "Detail"), p("d"), h(2, "Program code: Compile group"), c("```\nb();\n```"), h(2, "Results")]

def test_sections_numbering_and_nesting():
    secs = split_sections(PAGE)
    assert [s.number for s in secs] == [0, 1, 2, 3, 4, 5]
    assert [b.text for b in secs[2].blocks] == ["## Program code: Compile one", "```\na();\n```", "### Detail", "d"]

def test_select_by_prefix_returns_all_matches_in_order():
    texts = [b.text for b in select_sections(PAGE, "program code")]
    assert texts[0] == "## Program code: Compile one" and "## Program code: Compile group" in texts
    assert "## Results" not in texts

def test_select_by_number_and_lead():
    assert [b.text for b in select_sections(PAGE, 0)] == ["lead"]
    assert select_sections(PAGE, 3)[0].text == "### Detail"

def test_nested_match_returns_outer_once():
    blocks = [h(2, "Export"), p("x"), h(3, "Export: blocks"), p("y")]
    assert [b.text for b in select_sections(blocks, "export")] == ["## Export", "x", "### Export: blocks", "y"]

def test_partial_after_colon_does_not_match():
    with pytest.raises(ValueError, match=r"2\. ## Program code: Compile one"):
        select_sections(PAGE, "Program code: Compile")

def test_markup_in_heading_matches_plain_text():
    blocks = [h(2, "**Properties** of Safety telegrams"), p("x")]
    assert select_sections(blocks, "properties of safety telegrams")[1].text == "x"

def test_no_headings_and_bad_number():
    with pytest.raises(ValueError, match="no headings"):
        select_sections([p("x")], "Anything")
    with pytest.raises(ValueError):
        select_sections(PAGE, 9)
    with pytest.raises(ValueError):
        select_sections(PAGE[1:], 0)   # no lead → 0 is invalid

def test_code_view_groups_under_nearest_heading():
    blocks = [c("```\nlead();\n```"), h(2, "A"), c("```\n1\n```"), c("```\n2\n```"), h(2, "B"), p("x")]
    assert [b.text for b in code_view(blocks)] == ["```\nlead();\n```", "## A", "```\n1\n```", "```\n2\n```"]
    assert code_view([p("x")]) == []

def test_outline_rows():
    rows = outline_rows(PAGE)
    assert rows[0] == OutlineRow(0, "(before first heading)", len("lead\n"), 0)
    assert rows[2].code_blocks == 1 and rows[2].label == "## Program code: Compile one"
    assert outline_rows([p("x")])[0].label == "(whole page)"
    assert outline_rows([]) == []
```

- [ ] **Step 2: Run** `uv run pytest -q tests/test_reading.py`, expect FAIL (module missing).
- [ ] **Step 3: Implement** in `reading.py`.
- [ ] **Step 4: Run.** Expected: pass; ruff clean.
- [ ] **Step 5: Commit:** `feat: add section, outline and code views`

### Task 6: Block-boundary chunking (pure)

**Files:** Modify `siemens_docs_mcp/reading.py`, `tests/test_reading.py`.

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Chunk:
      text: str                 # ends with "\n" only when it reaches the end of the view
      next_offset: int | None   # None when nothing is left
  def chunk_view(blocks: Sequence[Block], offset: int, max_chars: int) -> Chunk
  ```
  Raises `ValueError("offset {offset} is past the end of this page (length {n}).")` when `offset >= n > 0`, where `n = len(view_text(blocks))`.
- Algorithm. Positions refer to `view_text(blocks)`; block *i* spans `[s_i, s_i + len(text_i))`; the final `"\n"` belongs to the last block.
  1. **Start.** An offset inside a separator moves to the next block's start. An offset inside block *i* moves to `s_i` if `len(text_i) <= max_chars`. Otherwise it moves to the start of its line, if that line is no longer than `max_chars` (clarification 3), or stays exactly at the offset.
  2. **Fill.** Append whole remaining blocks, with `"\n\n"` separators counted, while the total stays within `max_chars`. A block that doesn't fit but is no larger than `max_chars` ends the chunk. A block larger than `max_chars` is split to fill the remaining budget (clarification 4), unless no split point fits; then the chunk ends.
  3. **Split points**, chosen as the last that fits: line boundaries. For a code block, the chunk piece ends with a ```` ``` ```` line, and a piece starting after the first line begins with ```` ``` ````. For a table, a piece starting after line 2 begins with the header and separator lines, if they plus one row fit; otherwise without them. For a single line longer than the budget: the last space, else a hard cut at the budget. Synthetic fence and header lines count toward `max_chars` but not toward offsets.
  4. Every chunk returns at least one character of the view. `next_offset` is the view position of the first character not returned.

- [ ] **Step 1: Write failing tests**

```python
def _all(blocks, max_chars, offset=0):
    """Concatenate chunk payloads (synthetic fence/header lines removed) until done."""
    ...  # loop chunk_view, strip lines added by the splitter, return (pieces, joined)

def test_whole_blocks_only():
    blocks = [p("a" * 600), p("b" * 600)]
    first = chunk_view(blocks, 0, 1000)
    assert first.text == "a" * 600 and first.next_offset == 602

def test_oversized_code_is_split_with_valid_fences():
    code = c("```\n" + "\n".join(f"line {i:03d}" for i in range(300)) + "\n```")
    chunk = chunk_view([code], 0, 1000)
    assert chunk.text.startswith("```\n") and chunk.text.endswith("\n```") and len(chunk.text) <= 1000
    second = chunk_view([code], chunk.next_offset, 1000)
    assert second.text.startswith("```\nline ")

def test_table_continuation_repeats_header():
    rows = "\n".join(f"| r{i} | {'v' * 40} |" for i in range(60))
    table = Block("table", "| h1 | h2 |\n| --- | --- |\n" + rows)
    second = chunk_view([table], chunk_view([table], 0, 1000).next_offset, 1000)
    assert second.text.startswith("| h1 | h2 |\n| --- | --- |\n| r")

def test_long_paragraph_splits_at_space_and_progresses():
    para = p("word " * 1000)
    offsets, offset = [], 0
    while offset is not None:
        chunk = chunk_view([para], offset, 1000)
        assert 0 < len(chunk.text) <= 1000
        offsets.append(offset)
        offset = chunk.next_offset
    assert offsets == sorted(set(offsets))

def test_single_spaceless_line_hard_cut():
    chunk = chunk_view([p("x" * 2500)], 0, 1000)
    assert chunk.text == "x" * 1000 and chunk.next_offset == 1000

def test_title_then_huge_paragraph_fills_first_chunk():
    chunk = chunk_view([h(1, "Page 1"), p("abcdefghij " * 400)], 0, 1000)
    assert len(chunk.text) > 900

def test_offset_mid_block_snaps_back_and_separator_moves_forward():
    blocks = [p("a" * 300), p("b" * 300)]
    assert chunk_view(blocks, 450, 1000).text.startswith("b" * 300)
    assert chunk_view(blocks, 301, 1000).text.startswith("b")

def test_changed_max_chars_resumes_without_loss():
    blocks = [p(f"para {i} " + "z" * 200) for i in range(30)]
    first = chunk_view(blocks, 0, 3000)
    rest = _all(blocks, 1000, offset=first.next_offset)[1]
    assert first.text + "\n\n" + rest == view_text(blocks)

def test_concatenation_reproduces_view():
    blocks = [h(1, "T"), p("x " * 900), c("```\n" + "y\n" * 800 + "```"), p("end")]
    assert _all(blocks, 1000)[1] == view_text(blocks)

def test_final_chunk_and_past_end():
    assert chunk_view([p("short")], 0, 1000) == Chunk("short\n", None)
    with pytest.raises(ValueError, match="length"):
        chunk_view([p("short")], 6, 1000)
```

  `_all` is the test's own helper. It loops `chunk_view`, removes the splitter's synthetic fence and header lines, and joins the pieces using the gaps between consecutive offsets.
- [ ] **Step 2: Run**, expect FAIL.
- [ ] **Step 3: Implement** `chunk_view` per the algorithm above.
- [ ] **Step 4: Run.** Expected: pass.
- [ ] **Step 5: Commit:** `feat: chunk pages at block boundaries`

### Task 7: Wire `read_page`, server schema, docs and size ceilings

**Files:** Modify `rendering.py`, `tools.py`, `server.py`, `README.md`; test `tests/test_rendering.py`, `tests/test_tools.py`, `tests/test_server.py`; create `tests/test_reading_sizes.py`.

**Interfaces:**
- Consumes: Tasks 4-6.
- Produces in `rendering.py`:
  - `render_outline(total_chars: int, rows: Sequence[OutlineRow]) -> str`. Header `Outline ({len(rows)} sections, {total_chars:,} chars):`, then one row per line: `{number}. {label} — {chars:,} chars`, plus `, {k} code block` or `, {k} code blocks` when k > 0. No rows → `This page has no content.`
  - `render_continuation(next_offset: int, section: int | str | None, mode: ReadMode) -> str` → `[truncated — call again with section="Program code", mode="code", offset=N]`. String sections go through `json.dumps`; ints are written bare. Arguments that aren't set are left out.
- Produces in `tools.py`:
  ```python
  def read_page(catalog, url, offset=0, max_chars=20000, *, reference_format="compact",
                section: int | str | None = None, mode: ReadMode = "full") -> str
  ```
  Validation runs before any request. Normalization: `""` → None; a digit-only string → int; negative int → error. Views:
  - full: title block, then body blocks, or the no-content line when there are zero blocks
  - full + section: `select_sections`
  - code: `code_view` over the body or the selected sections; empty → the line `No code blocks on this page.` or `No code blocks in the selected sections.`
  - outline: `render_outline(len(view_text(full view)), outline_rows(body))`

  The result is `render_page(...)` with the chunk text, plus `"\n\n" + render_continuation(...)` when `next_offset` is set.
- Server: `read_page(url, offset=0, max_chars=20000, reference_format="compact", section: int | str | None = None, mode: Literal["full", "outline", "code"] = "full")`. Description (plus the Task 4 links sentence, `_URL_DOC`, `_REFERENCE_DOC` and `hosts_doc`): "Read one documentation page as Markdown with a header (publication, version, breadcrumb, source reference). mode='outline' lists numbered headings with sizes. `section` takes an outline number or heading text (e.g. 'Program code', which also matches 'Program code: …') and returns only matching sections. mode='code' returns only code blocks under their headings and combines with `section`. Long results end with the exact arguments to continue."

- [ ] **Step 1: Write failing tests**

```python
# test_tools.py
def test_read_page_outline(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = OPENNESS_HTML
    out = read_page(catalog, "tia:tia2/tia2-p1", mode="outline")
    assert "\nOutline (5 sections, " in out
    assert "2. ## Program code: Compiling a technology object — " in out and "1 code block" in out

def test_read_page_section_and_code(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = OPENNESS_HTML
    sec = read_page(catalog, "tia:tia2/tia2-p1", section="Program code")
    assert "## Program code: Compiling the technology object group" in sec
    assert "Requirement" not in sec and "# Page 1" not in sec
    code = read_page(catalog, "tia:tia2/tia2-p1", section="2", mode="code")
    assert "## Program code: Compiling a technology object\n\n```" in code and "group" not in code

@pytest.mark.parametrize("kwargs", [
    {"mode": "outline", "section": "x"}, {"mode": "outline", "offset": 5}, {"mode": "summary"}, {"section": -1},
])
def test_read_page_argument_errors_fetch_nothing(catalog, fake_tia, kwargs):
    with pytest.raises(ValueError):
        read_page(catalog, "tia:tia2/tia2-p1", **kwargs)
    assert fake_tia.get_content_calls == []

def test_read_page_empty_string_args_are_unset(catalog):
    assert read_page(catalog, P1_URL, section="", mode="full") == read_page(catalog, P1_URL)

def test_read_page_empty_page_modes(catalog, fake_tia):
    fake_tia.contents[("tia2", "tia2-p1")] = " "
    assert read_page(catalog, P1_URL, mode="outline").endswith("This page has no content.")
    assert read_page(catalog, P1_URL, mode="code").endswith("No code blocks on this page.")
    with pytest.raises(ValueError, match="no headings"):
        read_page(catalog, P1_URL, section="x")

def test_read_page_section_hint_repeats_arguments(catalog, fake_tia):
    code = "".join(f'<p class="p_table_l_code">line {i}</p>' for i in range(400))
    fake_tia.contents[("tia2", "tia2-p1")] = f'<p class="Blocktitle">Program code</p><table class="table_sourcecode"><tr><td>{code}</td></tr></table>'
    out = read_page(catalog, P1_URL, section="Program code", mode="code", max_chars=1000)
    assert re.search(r'\[truncated — call again with section="Program code", mode="code", offset=\d+\]$', out)

# test_server.py: the read_page schema exposes `section` (accepting int and string) and `mode` (enum of the three
# values); calling the tool with section=2 and with section="2" returns the same text.
```

  Update `test_read_page_truncates_with_offset_hint` to the new semantics. The first chunk's hint offset must equal the length of its body text. Calling again with that offset must continue with the next character. The two chunks must concatenate to the full body. Keep `test_read_page_last_chunk_has_no_footer`, `test_read_page_offset_past_end` and `test_read_page_empty_content` unchanged.

  `tests/test_reading_sizes.py`: load `OPENNESS_HTML` as `tia2-p1` and measure six outputs: full in compact and in url format, outline, `section="Program code"`, code mode, and code mode combined with `section="Program code"`. Assert:
  - each is at most `ceil(measured * 1.05)`, with the measured values recorded as constants and in the evidence doc;
  - compact full < url full;
  - outline, section and code are each smaller than compact full;
  - the reference-output goldens in `reference_outputs.json` still pass (an existing test).
- [ ] **Step 2: Run**, expect FAIL.
- [ ] **Step 3: Implement** the rendering functions, `read_page`, and the server parameters and description. Update the README `read_page` row: "Read one page as Markdown: outline, sections by heading or number, code only; page through with `offset`". Add a short usage example under the existing compact-reference example.
- [ ] **Step 4: Run** `uv run pytest -q` and `uv run ruff check .`. Expected: all green.
- [ ] **Step 5: Commit:** `feat: add outline, section and code reading modes`

### Task 8: Live evidence and roadmap status

**Files:** Modify `tests/test_live.py`, evidence doc, `docs/superpowers/plans/2026-11-01-llm-efficiency-roadmap.md`, design doc status line.

- [ ] **Step 1: Extend `test_reading_measurements`.** For each pinned page also measure outline, `section="Program code"` (record the error text where a page has no such heading), and code mode. Assert that every compact body link (`](tia:…)`/`](iox:…)` in compact full output) reads successfully with `read_page`, and that no chunk in a paged read with `max_chars=1000` has an odd number of ```` ``` ```` lines.
- [ ] **Step 2: Run live.** Record before/after full-mode chars (Task 1 "before" vs now) and the new mode sizes in the evidence doc. Label them as live measurements with date, throttle and cache conditions. If a host is unreachable, record the gap.
- [ ] **Step 3: Update the roadmap.** Status: milestone 3 approved and implemented. Under point 3, add Design/Plan links. Update the design doc's status line.
- [ ] **Step 4: Full suite + ruff green, commit:** `docs: record structured reading evidence`
