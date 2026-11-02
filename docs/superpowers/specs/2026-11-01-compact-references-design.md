# Compact references: first-milestone design

Date: 2026-11-01
Status: approved by the user on 2026-11-02; this session remains planning-only.
Roadmap: [LLM efficiency roadmap](../plans/2026-11-01-llm-efficiency-roadmap.md).

## Intent

Make documentation addresses substantially smaller while preserving page access,
URL compatibility, and maintainable responsibilities. References must be usable
across sessions without a prior search/TOC call or a session-local registry.

## Agreed decisions and engineering choices

The user agreed to the roadmap sequence, staged delivery within milestone 1, and
self-contained references with stable host prefixes.

The precise spelling below, literal-host fallback, output-format parameter, and
handling of incomplete upstream results were proposed engineering choices and
are covered by the user's approval of this specification on 2026-11-02.

## Approaches considered

1. Add formatting branches directly to the existing tool functions. This is the
   shortest immediate change, but increases coupling as output modes accumulate.
2. Extract explicit boundaries in separately verified steps inside the feature
   milestone. This supports deterministic output tests and keeps new structure
   tied to real requirements. The user selected this approach.
3. Complete a comprehensive data/rendering refactor as a separate prerequisite
   milestone. This provides immediate consistency but risks designing a page
   model that will change again when structured reading is introduced.

## Reference contract

| Target | Example |
| --- | --- |
| TIA publication | `tia:<mapId>` |
| TIA topic | `tia:<mapId>/<contentId>` |
| Industrial Operations X publication/topic | `iox:<mapId>[/<contentId>]` |
| Additional configured host | `<full-hostname>:<mapId>[/<contentId>]` |

Square brackets in this table indicate an optional topic segment, not literal
syntax. `tia` and `iox` permanently identify the two existing built-in hosts:
`docs.tia.siemens.cloud` and `docs.industrial-operations-x.siemens.cloud`.
They never depend on configured-host ordering. No alias configuration is added.

Accept the full hostname as a prefix for any allowed host, including the built-in
hosts; emit the short alias for built-in hosts. Host prefixes are case-insensitive
and emitted lowercase. Map/topic identifiers retain their case.

An identifier segment must be nonempty, use the existing identifier character
set (letters/digits/underscore plus `~`, `.`, and `-`), and must not be `.` or `..`.
Compact references do not contain URL query strings, fragments, percent-encoded
paths, extra slashes, or extra segments. Trim surrounding whitespace only.
Existing URL parsing behavior is preserved rather than tightened incidentally.

Emit canonical content IDs whenever known. Continue accepting topic IDs used by
existing TOC links, preserving `find_path`'s contentId/tocId matching behavior.
Publication-only references retain the existing whole-publication TOC and
root/first-topic page-reading behavior.

Stateless does not guarantee upstream permanence: a reference identifies the
same host/map/topic independently of a server process, but deleted or changed
Siemens publications can still become unavailable.

## Public tool behavior

- Keep the existing four tool names and current required parameter names.
- `read_page(url=...)` and `get_toc(url=...)` accept either a reader URL or the
  compact form. Keep `url` to avoid breaking existing named callers.
- Search and publication listing retain their existing host-selection parameters.
- Add one optional `reference_format` parameter on all four tools:
  `compact` (default) or `url`. It changes emitted reference spelling only.
- In `url` mode, retain the current full-URL representation and current content
  fields. In compact mode, replace tool-generated reference fields with compact
  references. Do not emit both forms for each item by default.
- Preserve result ordering, limits, titles, breadcrumbs, excerpts, empty-result
  messages, provenance, and pagination behavior, apart from text that must explain
  accepted references or the chosen reference spelling.
- Page-body inline links remain unchanged in this milestone. Link-text-only
  rendering, compact link footers, section reading, and safe block pagination
  belong to milestone 3.

The format parameter controls tool-generated addresses; it does not claim that
an upstream page's body is free of inline URLs. Tool descriptions and README
examples must make the distinction clear.

## Architecture and ownership

### Catalog: identity and reference handling

Extend the existing `Catalog.resolve`, `map_url`, and `reader_url` boundaries.
Use the existing `Resolved` target model; do not create a parallel reference
object hierarchy. The catalog owns compact parsing and spelling, so individual
tools cannot independently invent reference formats.

Compact parsing runs before URL parsing. Resolve the prefix through the existing
allowed-host check. Reject malformed syntax and unknown/disallowed hosts before
network requests. Syntactically valid targets still use normal catalog lookup;
do not invent a separate publication registry or change existing unknown-topic
handling as part of this work.

Formatting a known target into a compact reference must not fetch metadata or a
TOC. Retain URL-generation ambiguity handling for full-URL mode.

### Tools: orchestration and normalization

Tool entry points retain request validation, retrieval, result selection, and
pagination coordination. Prepare the values required by formatting functions
before rendering. Renderers perform no client/catalog lookups.

Reuse `MapInfo`, `Resolved`, and `TocPage`. A small normalized search-hit record is
appropriate if needed to remove raw API keys and HTML excerpt parsing from the
renderer; do not add wrapper models solely to make all four outputs look alike.

For valid search hits, use the requested host and available map/content IDs to
construct references without loading each hit's TOC. If IDs are incomplete,
retain a valid allowed-host reader URL as a fallback rather than issuing extra
requests solely to shorten it. If neither form is available, preserve the hit's
content with an explicit unavailable-reference indication; never invent an ID.
Do not silently swallow malformed upstream values as successful normalization.

### Rendering: deterministic presentation

Extract focused formatting functions for the affected outputs. They receive
prepared values and produce Markdown without I/O. One small rendering module is
reasonable; exact function names and placement are left to the implementer.

Keep one shared implementation of content layout where only reference spelling
differs. A mode parameter does not justify separate copies of each tool renderer,
a renderer class hierarchy, a plugin registry, or a future JSON implementation.

Validation and lookup failures remain owned by tools/catalog. Keep the existing
central MCP error translation in `server.py`; renderer extraction must not add
exception swallowing or a second error boundary.

### Converter and CLI

Do not change the converter representation, HTML parsing pipeline, or exporter
architecture in this milestone. Keep the existing URL-based CLI configuration
working. Compact references are an MCP contract here; adding compact CLI config
support is outside this milestone and must not be implied by documentation.

## Staged delivery

### A. Baseline and behavior-preserving extraction

Capture representative current outputs and sizes. Extract normalization and
formatting boundaries while retaining current tool schemas and default outputs.
Run the relevant existing tests, examine the diff, and commit this structural
step independently before changing output behavior.

### B. Compact-reference behavior

Extend catalog parsing/generation, add the explicit output-format option, and
wire the four tools through the shared formatting boundary. Update affected
fixtures, tool schemas, examples, and tests. Keep URL output as the compatibility
path. Verify and commit this behavior separately from stage A.

### C. Qualification and evidence

Record fixture comparisons and fixed size ceilings alongside semantic tests.
Compare the same fixed live targets before/after when reachable. Qualification
must be tied to the candidate being reviewed and distinguish measured characters
from estimated or tokenizer-specific tokens. Do not promise a reduction ratio
before a representative baseline exists.

## Acceptance criteria

- Existing URL inputs continue to work, including ambiguous pretty URLs,
  publication-only URLs, topic aliases, and URLs absent from the TOC where the
  existing read behavior allows them.
- Every addressable result emitted by search, publication listing, TOC, or page
  provenance round-trips through the appropriate read/TOC path in both formats.
- Alias resolution remains correct across processes and configured-host order;
  literal-host references work only for allowed hosts.
- Invalid compact syntax/host and invalid format parameters are rejected before
  fetching. Existing validation and useful error hints remain covered.
- Tests assert required content and metadata independently of size, so empty or
  incomplete output cannot satisfy a size ceiling.
- Fixed long-path fixtures show smaller compact output than URL output. Exact
  character ceilings are set from the recorded baseline/candidate measurements
  and checked in with the renderer tests; no new tokenizer dependency is needed.
- Preserve current result caps and pagination contracts. No new unbounded
  retrieval or request-per-search-hit behavior is introduced.
- Search fixtures use coherent, configurable host/map/content identities. Current
  `make_hit` defaults cannot serve as proof of cross-host reference round trips.
- Existing URL-based export and MCP named arguments have regression coverage.
- Live evidence records actual targets, output formats, sizes, request/cache
  conditions, failures, and any fallback URL use. Unreachable hosts leave an
  explicit qualification gap, not an invented successful measurement.

## Scope boundaries and remaining builder choices

No session handles, new tools, scope filters, section/code modes, batching,
catalog persistence, alias configuration, generic rendering framework, or
legacy-script removal are included.

The implementer chooses exact helper/module names, the minimal normalized
search-hit representation, test organization, and measurement artifact format
within existing documentation/test conventions. These choices must preserve
the responsibilities and contracts above. The [detailed task plan](../plans/2026-11-02-compact-references.md)
identifies the exact files, verification commands, fixtures, and commit boundaries.
