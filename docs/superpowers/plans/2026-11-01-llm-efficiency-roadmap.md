# LLM efficiency roadmap

Date: 2026-11-01
Status: sequence and staged delivery approach agreed; milestone 1 design approved
on 2026-11-02. Later milestones require their own design review.
Source: [LLM efficiency guidance](../../llm-efficiency-guidance.md).

## Goal

Reduce the amount of documentation output an agent must retain and the number of
calls needed to find useful content, while preserving access to every page and
keeping the code easy to change.

The primary use is TIA Portal Openness documentation; the design must continue to
work for other publications and both built-in hosts. The guidance's token counts
are estimates, not a measured baseline for the current server.

## Delivery principles

- Keep the four existing tools and Markdown output.
- Group work by usable outcomes. Put prerequisite refactoring inside the
  milestone it supports, in separately verified commits.
- Reuse existing catalog, publication, target, and TOC models. Add a model only
  when it represents data that a concrete feature needs.
- Keep reference resolution in the catalog, request coordination in tools,
  presentation in deterministic formatting functions, and document structure in
  the converter.
- Preserve validation, informative errors, host restrictions, throttling, and
  existing URL inputs.
- Measure output size alongside content correctness. Smaller output that omits
  required content does not satisfy a milestone.
- Scope new public parameters to the feature being delivered. No generic output
  framework or speculative JSON format.

## 1. Compact references end to end

Outcome: references emitted by the tools can be reused as inputs without carrying
long reader URLs or requiring session-local handles.

Agreed decisions:

- References are stateless and self-contained, with stable host prefixes.
- Delivery is staged within this milestone: first extract the required
  data/rendering boundaries without changing behavior, verify that step, then
  introduce compact references and verify the new behavior.

Scope:

- Capture representative current output sizes before changing output.
- Extend existing catalog reference handling, preserving URL support.
- Emit compact references by default, with an explicit full-URL output option.
- Cover publication and topic targets, both built-in hosts, and configured hosts.
- Update tool schemas, guidance, examples, and fixtures affected by the contract.
- Verify reference round trips, legacy compatibility, content, and size budgets.

Exit: the approved reference contract works across all four tools; the structural
step and behavior step have independent verification; measured before/after
results distinguish fixtures from live evidence.

Design: [Compact references](../specs/2026-11-01-compact-references-design.md).
Detailed plan: [Milestone 1 implementation plan](2026-11-02-compact-references.md).

## 2. Scoped search

Outcome: after identifying a publication or topic, an agent can search within the
relevant publication or subtree instead of filtering unrelated hits manually.

First verify what the live Fluid Topics endpoint can express: the guidance's
suggested map/cluster metadata filter is an investigation lead, not a confirmed
API contract. Define publication and subtree semantics from that evidence.

Reuse the reference contract and normalized search results from milestone 1.
Preserve the existing unscoped search behavior when no scope is supplied.

Exit: scope is tested against unrelated publications/topics, and the implementation
states any upstream limitations rather than silently ignoring scope.

## 3. Structured page reading

Outcome: an agent can inspect a heading outline and read selected sections or code
without first consuming the beginning of a long page.

Scope:

- Introduce converter blocks carrying the structure needed by actual reading modes.
- Support heading outlines, section selection, and code-first reading.
- Make truncation respect semantic boundaries; retain the documented offset
  fallback, with its exact compatibility policy settled in this milestone's design.
- Support compact link handling while preserving link text and useful provenance.
- Remove duplicate HTML parsing where the structured conversion pipeline allows it.

Keep a string-producing conversion path for the existing exporter. Do not create
a second independent HTML converter.

Exit: headings, repeated headings, nested sections, long code blocks, lists,
tables, links, and empty pages have defined behavior and content/size tests.

## 4. Batch reading

Outcome: related pages can be read in one call with a shared output budget and
clear per-page provenance and outcomes.

Build on the reference contract and structured reading pipeline. Define budget
accounting, ordering, partial failures, and continuation behavior before coding.
Use the existing per-host throttling; batching must not bypass it.

Exit: multi-host and partial-failure batches retain addressable results and stay
within the defined budget without cutting through semantic blocks.

## 5. Lower operating overhead

Outcome: less repeated tool guidance and lower cold-start cost, with a simpler
exporter sharing the package's existing catalog and conversion behavior.

Scope:

- Move shared guidance into server instructions and shorten tool descriptions.
- Persist the catalog with explicit freshness, failure, and invalidation behavior.
- Simplify CLI catalog construction and use its TOC cache.
- Check the remaining root-script use before removing the duplicate legacy script.

These changes can be separate small deliveries within this milestone. Existing
configuration and export workflows need regression checks. Catalog persistence
intentionally revises the original design's no-disk-cache decision.

Exit: compare schema size, cold/warm startup, and exporter behavior using recorded
conditions; document cache recovery and freshness behavior.

## 6. Reassess a local corpus

Outcome: a decision about whether disk-backed reading and local search justify
their ingestion, freshness, provenance, and indexing costs.

Use measurements from the earlier milestones. The exported Markdown tree is a
starting point, not proof that a complete local serving/search solution exists.
Proceed only after a separate design; no local index or backend abstraction is
part of milestones 1-5 merely to prepare for this possibility.

## Verification across milestones

- Maintain offline content and compatibility tests plus explicit fixture-size
  ceilings for output formats being changed.
- Record characters as a deterministic size metric. Label any estimated tokens
  and name a tokenizer if actual token counts are recorded.
- Use the same fixed live targets before and after each behavior change when
  reachable. Preserve request throttling and record failures and cache conditions.
- If live hosts are unreachable, finish useful offline work and report the live
  evidence gap; fixture measurements cannot replace a live claim.
- Keep implementation limited to the milestone being executed. Each later
  milestone receives its own design and detailed plan.
