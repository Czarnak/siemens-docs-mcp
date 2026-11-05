# Scoped search: milestone 2 design

Date: 2026-11-05
Status: draft for user review.
Roadmap: [LLM efficiency roadmap](../plans/2026-11-01-llm-efficiency-roadmap.md), point 2.

## Intent

Once an agent has found the right publication, or a chapter in it, it should be
able to search only there. Today it searches the whole host and has to ignore
hits from unrelated manuals (for example, a `GetAttribute` search on the TIA host
returns hits from six publications, which have to be filtered by eye). Scoped
search removes that step and the extra calls it costs.

## Goals, non-goals, anti-goals

Goals:

- `search_docs` accepts an optional scope: a publication or a topic (subtree)
  reference, as a compact reference or reader URL.
- A publication scope returns hits from that publication only.
- A topic scope returns hits only from that topic and its descendants in the TOC.
- When a result count is partial, the output says so.

Non-goals:

- No new tool. No new output format.
- No scoping across several publications in one call.
- No local search index.

Anti-goals (a failure even if it technically works):

- Scope silently ignored: unrelated hits returned as if they were in scope.
- Unscoped search output or behavior changes.
- A subtree count presented as exact when it is not.

## Live API evidence (2026-11-05)

Probed `POST /api/khub/clustered-search` on `docs.tia.siemens.cloud` and
`docs.industrial-operations-x.siemens.cloud`:

| Finding | Evidence |
| --- | --- |
| Every topic hit carries `ft:publicationId` metadata equal to its `mapId`. | Both hosts. |
| Filter `{"key": "ft:publicationId", "values": [<mapId>]}` returns hits from that map only. | TIA: `GetAttribute` 137 → 11 hits, one map. IOX: `OPC UA` 6861 → 251 hits, one map. |
| An unknown filter key is **silently ignored** (full unfiltered results, no error). | `ft:nonexistent` returned the same 137 hits as no filter. |
| An unknown map id returns zero hits. | `ft:publicationId=doesnotexist` → 0. |
| No metadata key describes TOC position, so a subtree cannot be filtered upstream. | Inspected all ~50 metadata keys per hit on both hosts. |
| Publication-scoped results have one entry per cluster, and pages do not overlap. | IOX: pages 1, 2 and 6 at 50/page; page 6 has `isLastPage: true`. |
| `perPage=100` is accepted. | IOX returned 100 clusters. |
| Hit `contentId` values match cached TOC `content_id` values. | Openness V20: 50/50 hits found in the TOC. |

## Approaches

1. **Publication scope only.** Topic references are rejected with an error.
   Fully backed by the API, smallest change, but doesn't cover "I found the
   right chapter".
2. **Publication scope upstream, subtree filtered locally.** Search the publication,
   then keep only hits whose topic is in the subtree of the cached TOC, scanning a
   bounded number of result pages. Covers both cases; adds paging and
   partial-count reporting. **Chosen by the user.**
3. Subtree through query rewriting (for example, adding the chapter title to the
   query). Rejected: it changes relevance and doesn't guarantee scope.

## Design

### Parameter

`search_docs` gains `scope: str | None = None` (server tool and `tools.search_docs`).
It accepts exactly what `read_page`/`get_toc` accept in `url`, resolved with
`Catalog.resolve`. As elsewhere, `""` counts as unset.

### Interaction with the other parameters

- **host:** the scope decides the host. If `host` is also given and differs →
  error. The server currently fills in the default host before calling the tool;
  with a scope present it must not.
- **locale:** if unset, use the scoped publication's locale (so a `de-DE`
  publication works without also passing `locale`). If set explicitly and it
  differs from the publication's locale → error.
- **product / version:** rejected together with a scope, with an error saying the
  scope already selects one publication. *(My call: an error is clearer than
  silently ignoring them or applying a redundant filter.)*
- **limit, reference_format:** unchanged meaning.

### Publication scope

One upstream request with the publication filter (plus locale), `perPage = limit`.
No TOC request is needed.
The total comes from upstream and is exact.

### Topic (subtree) scope

1. Find the node with `find_path` (accepts contentId or tocId, same as `get_toc`).
   Not in the TOC → the same error `get_toc` gives. If the node is the
   publication root, treat it as publication scope.
2. Collect the subtree's content ids (the node and all descendants).
3. Request publication-scoped pages at `perPage = 100`. Keep hits whose
   `contentId` is in the subtree, in upstream relevance order.
4. Stop when `limit` hits are kept, the last page is reached, or after
   **3 pages (300 publication hits)**. *(My call: at the default 0.3 s throttle
   this is at most ~1 s of extra wait plus response time; see Open points.)*
5. The count is exact only when every publication hit was checked.

### Guarding against an ignored filter

Because the API ignores filters it doesn't understand, every cluster in a scoped
response must contain an entry from the scoped map. If one doesn't, raise an error
saying the host did not apply the publication filter. Don't drop the hit silently.
For each cluster, pick the entry whose `mapId` matches the scope rather than the
first entry.

### Output

Unscoped output is unchanged, byte for byte.

Scoped headers name the scope instead of the host:

```
Found 11 results for "GetAttribute" in Functions for SINUMERIK ONE (V20). Showing 10:
Found 4 results for "GetAttribute" in "Export/import" — TIA Portal Openness: … (V20). Showing 4:
Showing 10 results for "Device" in "TIA Portal Openness API" — TIA Portal Openness: … (V20); checked 300 of 812 publication results, more may exist:
No results for "zzz" in Functions for SINUMERIK ONE (V20).
No results for "Telegram" in "Basics" — TIA Portal Openness: … (V20) among the first 300 of 812 publication results. Try a narrower query or search the whole publication.
```

In scoped output, each hit drops the repeated "— publication (version)" suffix,
because the header already names it. Breadcrumb, excerpt and reference stay.
*(My call, following the guidance's "provenance once per result" principle.)*

### Where the code goes

- `catalog.py`: no change. `resolve` already handles the scope input.
- `tools.py`: scope resolution, parameter checks, request coordination, paging,
  subtree filtering and the filter guard. Unscoped requests take the existing path.
- `rendering.py`: scoped header variants and the per-hit suffix rule, as pure
  functions.
- `server.py`: new parameter, one sentence of tool description, and no default
  host/locale when a scope is given.
- `client.py`: no change. `search` already takes filters, page and perPage.

## Verification

Offline (fake clients):

- Publication scope sends the filter, derives host and locale, and renders the
  scoped header.
- Errors: host conflict, locale conflict, product/version with scope, topic not
  in the TOC, invalid scope reference.
- Subtree: filtering, tocId input, root behaves as publication scope, stop at
  `limit`, stop at the last page, stop at the page cap with a partial count, zero
  results after a partial scan.
- Filter guard: a cluster without a scoped-map entry raises an error.
- `reference_format="url"` works with scope.
- Existing unscoped tests and size baselines pass unchanged.
- Fixture size ceiling for scoped output.

Live (opt-in, like the existing live tests), on both built-in hosts using the
fixed live targets:

- A publication scope returns only references to that map, and fewer hits than
  unscoped search. This is the guard against upstream silently dropping the filter.
- A topic scope returns only references inside that subtree.

Docs: README `search_docs` row, tool description, and roadmap status.

## Delivery

Small enough to skip a separate detailed plan document: implement in a few
test-first commits on this branch (tools + rendering, server + docs, live tests),
running the full offline suite after each.

## Open points for the builder

- Exact wording of errors and headers may be tuned, provided the meaning above
  holds and the size ceiling is met.
- The page cap (3 × 100) is a module constant. Adjust it if live timing shows it
  is too slow or too shallow, and record why.
