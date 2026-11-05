# Structured page reading: milestone 3 design

Date: 2026-11-05
Status: approved by the user on 2026-11-05; implemented on branch `claude/wizardly-franklin-86xo5s`
(see the plan's "Clarifications to the spec made while planning").
Roadmap: [LLM efficiency roadmap](../plans/2026-11-01-llm-efficiency-roadmap.md), point 3.

## Intent

An agent reading a documentation page should be able to get the part it needs (the code, one
named section, or just the list of headings) instead of the whole page from the top, and page
links should cost fewer characters. Every tool result stays in the agent's context and is re-sent
on later turns, so a smaller `read_page` result is paid back many times over.

The main use is TIA Portal Openness documentation. The design must keep working for other
publications and for both built-in hosts.

## Live evidence (2026-11-05)

Sampled with the current converter: 120 random pages from TIA Portal Openness V20
(`docs.tia.siemens.cloud`, 655 pages) and 40 from Industrial Information Hub V2.7
(`docs.industrial-operations-x.siemens.cloud`, 1729 pages). Sizes are Markdown characters.

| Finding | Evidence |
| --- | --- |
| Openness pages are short. | Median 2.2k, p90 6.5k, max 14k in the sample (18k seen in a smaller sample). None over the 20k default `max_chars`. |
| IIH pages are shorter and have no headings inside the body. | Median 0.5k, p90 1.3k; only the title heading. |
| Openness pages follow a template of flat `##` headings from Siemens `Blocktitle` paragraphs; no `h1`–`h6` tags appeared. | Top headings: Program code (111), Requirement (89), Introduction (55), Application (41), Parameter (9), Example (6). |
| "Program code" repeats on a page, usually as "Program code: <task>". | e.g. "Compiling technology object" has two. |
| Code is about a third of Openness text. | 36k of 106k characters in a 30-page sample. |
| Most Openness body links point to other topics in id form. | 249 of 296 links are `https://<host>/r/<mapId>/<contentId>`; most others are image or attachment URLs (160–360 chars each). |
| On IIH, link URLs are about 30% of page text. | 7.9k of 27k characters; mostly image/attachment URLs. |
| Image links are often an `<a href=".../viewer/attachment/...">` around `<img alt="">`. | Openness "Export/Import of sub modules". |

Consequence: the "read 20k characters from the top" problem in the guidance only appears when an
agent lowers `max_chars`. Most of the gain comes from selecting by intent (code, a named section)
and from lighter links. Block-boundary cutting is still required, because any cut must be safe.

## Goals, non-goals, anti-goals

Goals:

- `read_page` can return a heading outline with sizes, selected sections, or only the code.
- Every cut falls between blocks; an oversized block is split at a line or table row, never inside
  a line, and fences/tables stay valid.
- Topic links in page bodies become compact references by default; image URLs are dropped.
- The page HTML is parsed once per read.
- The exporter keeps a string-producing conversion path with unchanged output.

Non-goals:

- No new tool. Batch reading is milestone 4.
- No numbered link footer, no resolving pretty-URL links or links to other hosts.
- No code-language guessing, no image extraction.
- No changes to search, TOC, or publication listing output, and no server-instructions work
  (milestone 5).

Anti-goals (a failure even if it technically works):

- A default `read_page` call whose output changes beyond the link rule below.
- Exporter (CLI) output that changes at all.
- A cut inside a code fence, table row, or line (except the documented last resort for a single
  line longer than the budget).
- A `section` that matches nothing returning an empty or silent result.
- A second, independent HTML-to-Markdown converter.

## Approaches

Chosen by the user: **A**.

- **A. The converter returns a flat list of blocks.** Each block carries its kind, heading level
  and finished Markdown. Reading modes are small pure functions over the list; `html_to_markdown`
  becomes "blocks, joined". Moderate refactor of converter internals; block Markdown stays
  identical because each block still goes through today's render functions.
- B. Keep the converter and split its Markdown output back into blocks. Less work up front, but it
  parses our own output (fragile around lists, quotes and fences), still needs a link hook in the
  converter, and contradicts the roadmap's "converter blocks / no second converter" rule.
- C. The converter returns a nested section tree. Sections come for free, but it is more model than
  any reading mode needs; a flat list with heading levels gives sections in a few lines.

## Design

### Public surface: `read_page`

```
read_page(url, offset=0, max_chars=20000, reference_format="compact",
          section=None, mode="full")
```

- `mode`: `"full"` (default), `"outline"` or `"code"`.
- `section`: `str | int | None`. An `int`, or a string of only digits, is a section number from
  the outline. Any other string is heading text. `""` counts as unset, as elsewhere.
- Existing parameters keep their meaning and validation.

Allowed combinations:

| mode | section | offset | Result |
| --- | --- | --- | --- |
| full | – | any | Whole page, chunked (today's behavior apart from links and block-boundary cuts). |
| full | set | any | Matched sections, chunked. |
| code | – | any | All code blocks, each under its nearest heading, chunked. |
| code | set | any | Code blocks within the matched sections only. |
| outline | – | 0 | The outline. |
| outline | set, or offset > 0 | – | Error: outline takes neither `section` nor `offset`. |

An unknown `mode` is an error naming the allowed values.

### Blocks

New in `converter.py`:

```python
BlockKind = Literal["heading", "paragraph", "code", "table", "list", "quote", "other"]

@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str          # finished Markdown for this block, no surrounding blank lines
    level: int = 0     # 1-6 for headings, 0 otherwise
```

- `html_to_blocks(source, *, link=None, images=True) -> list[Block]` where `source` is a cleaned
  `BeautifulSoup` (or an HTML string, parsed once). It does not include the page title.
- Wrapper `div`s and unknown container tags are opened: their block children become separate
  blocks, in order. Admonition divs and safety tables are one `quote` block. A list (with nested
  lists) is one `list` block. A table is one `table` block; `table_sourcecode` tables, `pre`, and
  `p_table_l_code`/`table_sourcecode` paragraphs are `code` blocks. `Blocktitle`/`BlocktitleFirst`
  paragraphs and `h1`–`h6` are `heading` blocks (levels as today: Blocktitle → 2).
- Block Markdown is produced by today's render functions, so the text is identical.
- The current adjacent-duplicate removal inside a `div` is kept, applied to its child blocks.
- `html_to_markdown(html, title, *, link=None, images=True) -> str` stays. It returns exactly
  today's string: `# {title}\n\n` + blocks joined with `\n\n` + post-processing, and the existing
  empty-page text. Post-processing (blank-line collapsing, trailing whitespace) is applied
  per block so joining blocks gives the same result as today.

### Link and image hooks

The converter never learns about reference formats.

- `link: Callable[[str], str | None] | None`. Called with each anchor `href`. A string replaces
  the href; `None` drops the URL and keeps only the label; no hook keeps the href unchanged.
- `images: bool`. When `False`, an image renders as its alt text only (empty alt → nothing), both
  standalone and inside links. When an anchor's label comes out empty, nothing is emitted.

`read_page` passes a hook built from a new catalog method:

- `Catalog.compact_link(url: str) -> str | None`: for an absolute URL on an allowed host with path
  `/r/<mapId>/<contentId>` or `/r/<mapId>`, where the segments are valid ids, return the compact
  reference. Pure text processing: no catalog or TOC fetch, no check that the map exists (a
  dangling compact reference fails later exactly like the URL would). Anything else → `None`.
- Attachment and resource URLs on an allowed host (`/viewer/attachment/...`,
  `/api/khub/maps/.../resources/...`) → drop the URL, keep the label.

Rules applied by `read_page`:

| Link target | `reference_format="compact"` | `reference_format="url"` |
| --- | --- | --- |
| Allowed host, `/r/<mapId>[/<contentId>]` | compact reference | unchanged URL |
| Allowed host, attachment/resource | label only | label only |
| Anything else (pretty URLs, `access?...`, other hosts, relative) | unchanged | unchanged |
| Images | alt text only | alt text only |

The CLI passes no hook and `images=True`, so exported Markdown is unchanged.

### Parse once

`content.py` gets `fetch_soup(client, map_id, content_id) -> BeautifulSoup | None`: fetches, parses
once, removes chrome in place, returns the tree (`None` for empty content). `fetch_html` remains as
a thin wrapper returning `str(soup)` until nothing uses it. `read_page` and the CLI both switch to
`fetch_soup` → `html_to_blocks`/`html_to_markdown`. A test asserts both paths give identical
Markdown for every fixture.

### Sections

Computed in a new pure module `reading.py` over the block list.

- Section 0 is every block before the first heading (the lead). It is listed only if non-empty.
- Each heading starts section *n* (1-based, in document order). A section runs until the next
  heading of the same or a higher level (smaller or equal number), so nested headings stay inside
  it.
- Heading match text is the heading with Markdown markup removed (`**`, `*`, backticks, link
  syntax) and whitespace collapsed. A text `section` matches, case-insensitively, a heading whose
  match text equals it, or starts with it followed by `:`. `"Program code"` matches "Program code"
  and every "Program code: …".
- All matching sections are returned, in document order. When a matched section is nested inside
  another matched section, only the outer one is returned.
- A number must be one of the outline's numbers (0 only if the lead exists).
- No match → error listing the page's headings with their numbers (and close matches first, using
  the same `difflib` approach as catalog errors). A page with no headings → error saying so and
  suggesting a read without `section`.
- Known limitation: a heading consisting only of digits can only be selected by its number.

### Outline output

Provenance header as today, then:

```
Outline (5 sections, 2,335 chars):
0. (before first heading) — 180 chars
1. ## Requirement — 210 chars
2. ## Program code: Compiling a technology object — 640 chars, 1 code block
3. ## Program code: Compiling the technology object group — 720 chars, 2 code blocks
4. ## Compile results — 585 chars
```

- The total is the size of the full-mode body. A section's size counts its own blocks and nested
  sections, joined as they would be returned. The code-block count is shown only when non-zero.
- Headings keep their `#` markers to show nesting; long headings are not shortened.
- A page without headings lists only section 0, labeled `(whole page)`. An empty page says
  `This page has no content.`

### Full, section and code views

Each non-outline call builds a **view**: a list of blocks, then chunks it.

- Full view without `section`: the title heading block (`# {title}`) followed by all body blocks,
  so the text matches today's body. An empty page keeps today's `*No content available.*` line.
- Empty page in the other modes: outline says `This page has no content.`; code view gives the
  no-code note; `section` gives the no-headings error.
- Section view: the matched sections' blocks, in order, without the page title (the header path
  already names the page).
- Code view: for each code block in scope, its nearest enclosing heading (emitted once per run of
  code blocks under the same heading; omitted for code in the lead) followed by the block. No code
  in scope → a single line, `No code blocks on this page.` or `No code blocks in the selected
  sections.`
- Known limitation: code that the converter renders inside a list or quote is not a `code` block
  and is not included in code view.

### Chunking and `offset` (compatibility policy)

`offset` stays a character position, counted in the view's text (blocks joined with `\n\n`).
`max_chars` bounds the chunk body, excluding the header and the continuation line, as today.

1. **Start.** If `offset` falls inside a block, start at that block's start, unless the block is
   larger than `max_chars`; then start at the beginning of the line containing `offset` within that
   block (resume of a split block, below). An offset in a separator starts at the next block. An
   offset at or past the end of a non-empty view is an error, as today.
2. **Fill.** Add whole blocks while the chunk stays within `max_chars`.
3. **Oversized block.** If the first block does not fit, split it at the last line boundary that
   fits: a code block is closed with a fence and the continuation reopens it; a table chunk ends
   between rows and the continuation repeats the header and separator rows; other blocks split at
   a line, or at the last space for a single long line. A single line with no space that is longer
   than the budget is cut at `max_chars` (last resort).
4. **Continue.** If anything is left, append
   `[truncated — call again with offset=N]`, where N is the view position of the first character
   not returned. In section or code view the hint repeats the arguments needed to get the same
   view, e.g. `[truncated — call again with section="Program code", mode="code", offset=N]`.

Compatibility: existing calls with no new parameters and offsets that came from earlier hints keep
working. A chunk may end earlier than `max_chars` and may start slightly before a supplied offset
when that offset was mid-block. Nothing else about full mode changes.

### Where the code goes

- `converter.py`: `Block`, `html_to_blocks`, hooks; `html_to_markdown` built on blocks.
- `content.py`: `fetch_soup`; `fetch_html` as a wrapper.
- `catalog.py`: `compact_link`.
- `reading.py` (new, pure): sections, matching, views, outline data, chunking.
- `rendering.py`: outline rendering and the continuation line; `render_page` unchanged.
- `tools.py`: `read_page` parameter checks and coordination; builds the link hook.
- `server.py`: new parameters; one or two sentences in the `read_page` description; the
  "Page-body links are unchanged" sentence is replaced.
- `cli.py`: switch to `fetch_soup`; no output change.
- README `read_page` row, roadmap status.

## Delivery

Staged like milestone 1, each step its own verified commits, offline suite green after each:

1. **Structural, no behavior change.** Blocks, hooks (unused), `fetch_soup`, both callers switched.
   Verify: all existing tests and size baselines pass unchanged; for every HTML fixture,
   `html_to_markdown` output is byte-identical to the previous implementation; same check on the
   live Openness/IIH sample when reachable, with the result recorded.
2. **Links.** `compact_link`, the read hook, image alt-only. Verify: rules table above, `url` mode,
   CLI unchanged, size ceilings for the fixture page.
3. **Reading modes.** Sections, outline, code view, chunking, server/docs.

## Verification

Offline:

- Blocks: kinds and levels for headings (h1–h6, Blocktitle), code (all four sources), tables,
  lists, safety tables, admonitions, nested divs, duplicate removal, empty pages.
- Byte-identical `html_to_markdown` against recorded outputs of the current implementation.
- Links: id-form topic link → compact, map-only link → compact, attachment → label, image in link
  with empty alt → nothing, pretty URL / `access?` / external / relative unchanged, url mode.
- Sections: lead, nested sections, repeated headings, `Program code` prefix rule, markup in
  headings, number and digit-string addressing, out-of-range number, no match with heading list,
  no headings, nested matches deduplicated.
- Outline: sizes, code counts, no headings, empty page.
- Code view: nearest heading, grouping, no code, code + section.
- Chunking: whole blocks only; oversized code (fence reopened), table (header repeated), long
  paragraph, single long line; offset mid-block snaps back; offset inside an oversized block
  resumes at its line; offset in separator; past-end error; hint wording per view; chunk
  concatenation reproduces the view without loss.
- Argument errors: outline + section/offset, unknown mode, `""` as unset.
- New HTML fixture modeled on an Openness page (lead, Requirement, two "Program code: …" sections
  with code tables, a topic link, an attachment-wrapped image), with character ceilings for full
  (compact and url), outline, `section="Program code"`, and code mode.
- Existing `reference_outputs.json` cases pass unchanged.

Live (opt-in, like the existing live tests), using the fixed live targets plus a recorded set of
Openness pages (including "Compiling technology object" and "Export/Import of sub modules"):

- Before/after full-mode sizes (link savings), and outline, section and code sizes, recorded in an
  evidence note like milestone 1's, labeled as live measurements with date and throttle settings.
- Every compact link emitted in a live page resolves with `read_page`.

## Calls left to the builder

- Exact wording of errors, the outline header, and the no-code notes, within the meaning above.
- Internal helper names and how `reading.py` is split into functions.
- Whether `fetch_html` is removed in this milestone once unused, or left for milestone 5's CLI
  cleanup.
