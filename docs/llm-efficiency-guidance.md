# LLM-friendliness and token-efficiency guidance

Date: 2026-11-01
Status: general direction, not a plan. Individual items get their own design discussion before implementation.

## Context

The server is used mostly to look up TIA Portal Openness API documentation while an agent writes
C# code, and increasingly for other publications (STEP 7, WinCC Unified, Industrial Operations X).
Every tool result lands in the agent's context window and is re-sent on every later turn, so the
cost of a result is paid many times over. The goal of this document is to set the direction for
making results smaller and tool calls fewer, without losing the ability to reach any page.

The numbers below come from the test fixtures and from the shape of the URLs the tools emit. The
Siemens hosts could not be reached from the environment where this was written, so treat them as
estimates to be confirmed with live measurements before and after each change.

## Principles

1. **Pay for content, not for addresses.** A reader URL is about 200 characters and tokenizes to
   roughly 65 tokens; the title next to it is 5 to 10 tokens. Addresses must be short, and the full
   URL should appear once per result (in a header), not once per line.
2. **Fewer, denser calls beat many small ones.** Each tool call replays the whole conversation.
   Prefer tool parameters that let the agent get what it needs in one call (scoped search, batch
   read, section selection) over tools that force a search, then a TOC, then a read.
3. **Cut at semantic boundaries.** Never split a result in the middle of a sentence or a code
   fence. Page through sections and headings, not character offsets.
4. **Default to compact, allow verbose.** The default rendering of every tool should be the
   smallest useful form. Full URLs, inline links, excerpts and metadata are opt-in through a
   parameter, never the default.
5. **Keep the agent oriented without repetition.** Provenance (publication, version, path) belongs
   in one header per result. Tool descriptions and shared guidance belong in the server's
   `instructions`, not repeated in every tool description.
6. **Measure.** Each output format gets a test that asserts an upper bound on characters for a
   fixed fixture, so regressions in size are caught like regressions in content.

## Where the budget goes today

| Output | Estimated size | Main cause |
|---|---|---|
| One pretty topic URL | ~65 tokens | Long human-readable path |
| `get_toc` depth 3, 300 lines | ~24k tokens | About 85% is URLs |
| `get_toc` at the 500-line cap | ~40k tokens | Same |
| `search_docs`, 10 hits | ~1.5k tokens | URL, breadcrumb and excerpt per hit |
| A short converted page | 350 to 460 tokens | Fine; inline links add ~20 tokens each |
| Four tool descriptions | ~400 tokens per turn, every turn | Hosts and filter guidance repeated 4 times |

## Direction for features

Ordered by expected value for the current usage (Openness first, other areas growing).

### Compact references

Introduce a short reference form that every tool emits and every tool accepts wherever a URL is
accepted today. Two candidates:

- Stateless: `mapId/contentId` (about 22 characters, valid forever, roughly 3x cheaper than a
  pretty URL).
- Stateful: a numbered handle within a publication (`#12`), roughly 10x cheaper but only meaningful
  after a TOC or search call in the same session.

The stateless form is the safe default. A handle scheme can be layered on later if measurements
show TOC output is still the bottleneck. Full URLs stay available through a parameter, since users
sometimes want to open a page in the browser.

### Scoped search

Let `search_docs` take a publication or subtree reference so an agent that has found the right
manual gets hits only from it. The Fluid Topics search endpoint already accepts metadata filters;
the map or cluster id is the likely key. This removes most of the "search, then filter by eye"
pattern in Openness sessions.

### Section-aware reading

Give `read_page` a way to return the heading outline of a page (with sizes) and a way to read one
heading's section. Keep character offsets as a fallback, but slice at block boundaries. For long
API pages this replaces reading 20,000 characters from the top to find one method.

### Code-first reading

Offer a mode that returns only the fenced code blocks of a page, each preceded by its nearest
heading. This matches the most frequent Openness intent: "show me the C# for X". It is cheap to
build once the converter emits blocks rather than one string.

### Batch read

Accept several references in one `read_page` call, with a shared size budget. Three related
Openness pages (the class, its members, an example) become one round trip.

### Link handling

Drop link URLs from page bodies by default and keep the link text. Offer a parameter to list the
links, as compact references, in a numbered footer. Keep inline URLs only on request.

### Server instructions and lean tool descriptions

Move the allowed hosts, the default locale and the filter guidance into the MCP server's
`instructions` field. Reduce each tool description to one or two sentences about what it returns
and what it accepts.

### Catalog on disk

Persist the per-host catalog (about 16 MB JSON, several seconds to load) with its timestamp, so a
fresh server process starts warm. This was a non-goal in the original design; the cost has become
visible now that MCP clients spawn one server per session.

### Local corpus (later)

The exporter already produces a Markdown tree. Serving that tree through the same tools (search
with a small local index, read from disk) would make Openness lookups free of network latency and
throttling. Worth revisiting once the compact formats are in place, since the two combine well.

## Direction for refactoring

These structural changes make the features above cheap to add and easy to test. They are listed in
the order they unblock each other.

1. **Separate data from rendering in `tools.py`.** Tool functions should produce small dataclasses
   (search hit, TOC node, page) and hand them to renderers. Compact, verbose and any future JSON
   output become different renderers over the same data, each with its own size test.
2. **Centralize reference handling in the catalog.** One place parses URL, `mapId/contentId` and
   any later handle form into a resolved target, and one place generates the compact form. Today
   URL generation is spread across `map_url`, `reader_url` and string formatting in the tools.
3. **Make the converter emit blocks.** Instead of one Markdown string, return a list of blocks
   with their heading level and a flag for code fences. Section paging, code-only mode and link
   footers all become filters over that list. Add a link-rewrite hook so the converter never has
   to know about reference formats.
4. **Parse the HTML once.** Chrome removal in `content.py` and conversion in `converter.py` each
   build a BeautifulSoup tree for the same page. Merge them or pass the tree through.
5. **Simplify the CLI.** It constructs its own catalog through a list-append factory and bypasses
   the catalog's TOC cache. It should take a catalog like the server does and iterate the cached
   tree.
6. **Remove the legacy root script.** `html_to_markdown_tia.py` is not part of the package and
   duplicates converter logic.
7. **Add size budgets to the test suite.** For each fixture and each renderer, assert a character
   ceiling. Keep a live smoke test that prints real sizes for a fixed set of Openness pages, so
   the estimates in this document can be replaced with measurements.

## What to keep

- The four-tool surface. Add parameters and modes before adding tools; the agent pays for every
  tool schema on every turn.
- Markdown as the primary output. Models read it well, and it is denser than JSON for prose.
- Error messages with close matches and next-step hints. They save round trips.
- Per-host throttling and the small request surface. The API is unofficial.
- Stdio transport and in-process state. Nothing here needs HTTP or a shared cache.

## Non-goals for now

- Guessing code-fence languages from content. A wrong tag misleads more than a missing one. If a
  publication-level default (Openness means C#) is wanted later, it should be explicit per
  publication.
- Extracting embedded images. Alt text is enough for the current use.
- Login or restricted content.
- Sources outside Fluid Topics.
