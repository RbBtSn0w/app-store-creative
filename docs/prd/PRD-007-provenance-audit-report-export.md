# PRD-007: Provenance Audit Report Export

**Status:** Implemented (Sprint 001; Studio rendering deferred)
**Date:** 2026-10-19
**Owner:** rbbtsn0w
**Depends on:** Artifact lifecycle records (existing evidence/receipt data)
**Priority:** P2

## Problem Statement

The product's positioning is provenance-first: every artifact has traceable
lineage via lifecycle records, receipts, and evidence files. But that data is
only accessible as JSON records queried one at a time — there is no
human-readable summary a user can hand to a reviewer, legal, or a stakeholder.
The differentiator exists in data but not as a deliverable.

Users affected: enterprise teams (the target segment from the competitive
analysis) who need to justify creative asset provenance to reviewers or
compliance. Frequency: per release or per audit. Cost of not solving: the
positioning claim stays a slogan; the enterprise buyer has no artifact to
evaluate.

## Goals

1. A user can export a human-readable audit report for a release (or a
   single artifact) summarizing the full provenance chain.
2. The report is self-contained (readable without access to the repo or
   record store).
3. The report is generated from existing records with no new data entry.

## Non-Goals

- Not building a hosted dashboard or web viewer — v1 is file export only.
- Not adding signatures or cryptographic attestation (possible P2 later;
  separate threat model needed).
- Not modifying how records are written — read-only over existing data.
- Not a PDF layout engine — Markdown output for v1 (portable, diffable,
  reviewable in PRs, consistent with repo conventions).

## User Stories

- As a release manager, I want to export an audit report for a release so
  that I can attach it to the release PR or share it with compliance.
- As an enterprise reviewer, I want a self-contained summary of where every
  asset came from, who approved it, and when, so that I can sign off without
  learning the CLI.
- As an agent, I want the report in Markdown so that I can post it as a PR
  comment or include it in a handoff document.

## Requirements

### Must-Have (P0)

- **R1**: A CLI command (e.g. `audit report`) takes a lifecycle run ID (`--run-id`) and emits a Markdown report covering: artifact inventory, per-artifact
  source lineage, receipts, approvals, and delivery/publication references.
  The report is summary-first: a top block with run ID, generation time,
  artifact/receipt counts, and gap summary precedes per-artifact detail.
  - *Acceptance*: Unit test with a fixture record store produces a report
    containing all sections with correct IDs and no "unknown" placeholders
    for data that exists in the store; the gap summary appears at the top.
- **R1a (P0)**: Records are read via the existing public query surfaces —
  per-run `status()` and per-delivery `delivery_status()` /
  `list_deliveries()` / `list_publications()` — composed into the report; no manual record
  traversal.
  - *Acceptance*: Report generation uses only those public query surfaces in
    the implementation under test.
- **R2**: Missing/incomplete provenance data is explicitly reported, not
  silently omitted.
  - *Acceptance*: Unit test with a record missing a receipt or approval
    asserts the report contains an explicit gap indicator for that artifact
    (and the top summary counts it).
- **R2a (P0)**: The summary block includes a machine-checkable integrity
  line (artifact vs. receipt counts, gap count) that a validator test can
  assert on.
  - *Acceptance*: A validator test parses the integrity line and asserts the
    counts match the fixture record store.

### Nice-to-Have (P1)

- **R3**: Studio can display the same report (render the Markdown) for a
  selected release, including the R2a integrity line.

### Future Considerations (P2)

- Cryptographic attestation (signed reports) for regulated teams.
- HTML/PDF rendering pipeline for external distribution.

## Success Metrics

- **Leading**: A complete audit report for a sample release can be generated
  in one command and passes review (all sections present, no silent gaps).
- **Lagging**: The report is used in at least one real release PR as
  evidence; enterprise-positioning content can reference a concrete
  deliverable.

## Open Questions

- *(engineering, resolved)* Per-run `status()` and per-delivery
  `delivery_status()` / `list_deliveries()` exist; the report composes them
  — no manual record traversal needed.
- *(product, non-blocking)* Should the report live in the repo (e.g.
  `docs/` or releases folder) or be emitted to stdout/file by user choice?
- *(product, batch-level)* This PRD targets enterprise/team reviewers while
  PRD-001 anchors the primary user as an indie developer; the batch-level
  user-segment sequencing decision is owned by PRD triage. The report stays
  useful for solo users either way.

## Timeline Considerations

- Read-only feature over existing data; low risk. Independent of other PRDs
  in this batch, but natural to land after PRD-004 so BGM receipts are
  complete in reports.
