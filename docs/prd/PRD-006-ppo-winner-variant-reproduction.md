# PRD-006: PPO Winner Variant → Production Reproduction

**Status:** Implemented v1 (Sprint 001; decision recording and Studio action deferred)
**Date:** 2026-10-19
**Owner:** rbbtsn0w
**Depends on:** PRD-004 (BGM lifecycle registration), `ppo handoff` CLI
**Priority:** P1 (top functional priority; effort L, v1 CLI-only)

## Problem Statement

The measurement→production loop is broken in the industry and in this
product: `ppo handoff` compiles `ppo-handoff.json` and an ASC execution plan,
but there is no path from "experiment concluded, variant X won" back to the
production pipeline that regenerates the winning creative at scale, per
locale, per target device. Today the user manually re-enters card data into
Studio or re-runs the pipeline with hand-copied parameters.

This is the structural gap identified in the competitive analysis: no
competitor closes the loop from a measured winner to reproducible
production. StoreMaven tests but does not produce; Screenshots.pro produces
but does not measure. Owning this loop is the product's clearest
differentiation opportunity.

## Goals

1. A concluded PPO experiment's winning variant can be reproduced into
   production-ready deliveries with a single command.
2. The reproduction is fully traceable: the produced artifacts reference the
   experiment ID, variant, and decision evidence in their receipts.
3. Reproduction works across all locales and targets defined in the
   original experiment scope.

## Non-Goals

- Not building a visual diff/comparison UI between variants (Studio view is
  a possible fast follow, not v1).
- Not automating ASC upload of reproduced variants — the ASC boundary stays
  as-is (evidence and plan out, no upload from this repo).
- Not changing the PPO scoring/statistics methodology.
- Not supporting "partial winners" (e.g. winning headline from variant A
  plus winning screenshot from variant B) — v1 reproduces a whole variant.

## User Stories

- As a growth engineer, I want to reproduce the winning variant of a
  concluded experiment into per-locale deliveries so that I can ship the
  measured winner without manual re-entry.
- As an agent orchestrating the pipeline, I want the winner reproduction to
  emit receipts that reference the experiment decision so that the
  provenance chain links measurement to production.
- As a release manager, I want to review which variant won and what will be
  reproduced, with a dry-run output, before committing storage writes.

## Requirements

### Must-Have (P0)

- **R1**: A `ppo reproduce` (or equivalent) command takes an experiment ID +
  an explicit `--variant` selection (no decision-data auto-selection in v1)
  and produces deliveries for every locale/target in the experiment scope.
  - *Acceptance*: Unit test with a fixture experiment reproduces the
    expected delivery set; each delivery receipt explicitly references the
    experiment ID, variant, and decision basis.
- **R1a (P0)**: The lifecycle record schema gains an experiment-provenance
  field (experiment ID, variant, decision basis) so receipts can carry the
  lineage above; this is an explicit schema/contract change, not an implicit
  one.
  - *Acceptance*: Receipt round-trip test asserts the provenance fields
    survive write/read in the lifecycle record store.
- **R1b (P0)**: Reproduction uses the existing per-treatment storage
  namespace strategy from `derive_treatment_config` (treatments remain
  namespaced; no shared-workspace mixing).
  - *Acceptance*: Unit test asserts reproduced artifacts land in the
    per-treatment namespace, matching the existing experiment layout.
- **R2**: The command supports a dry-run mode that lists what would be
  produced without writing. Default output is a human-readable review
  surface: provenance header (experiment ID, variant, decision basis),
  planned deliveries grouped by locale, and summary counts (locales ×
  targets); `--json` provides the agent-readable equivalent.
  - *Acceptance*: Dry-run output contains the provenance header, locale-
    grouped plan, and counts; no storage mutation occurs.
- **R3**: If any per-locale reproduction fails, the command reports partial
  success with per-locale status and does not mark the run complete.
  - *Acceptance*: Forced-failure unit test asserts per-locale status
    reporting and a non-complete run marker.

### Future Considerations (P2)

- ASC plan generation for reproduced variants (reuse existing
  `ppo handoff` plan machinery).
- Multi-variant combination ("winner cocktail") support.
- Decision-data recording (winner auto-selection when ASC results are
  ingested), replacing the explicit `--variant` requirement.
- Studio action surfacing winner reproduction (v1 is CLI-only).

## Success Metrics

- **Leading**: Time from "experiment concluded" to "reproduced deliveries
  ready" drops to a single command (< 1 minute for a typical 5-locale
  scope; the "minutes–hours manual" baseline is an unmeasured estimate).
- **Lagging**: 100% of reproduced deliveries carry experiment provenance in
  receipts; the measurement→production loop is demonstrable end to end in a
  recorded demo.

## Open Questions

- *(engineering, resolved)* No winner/decision record exists today (`ppo
  handoff` output carries no decision fields; there is no ASC result
  ingestion). v1 therefore requires explicit `--variant`; decision recording
  is a fast follow.
- *(engineering, resolved)* The production entry point is
  `production_lifecycle.produce()` (a single run already accepts targets and
  locales); no new bulk path in v1.
- *(product, resolved)* Reproduction always requires the explicit
  `--variant` selection in v1; auto-selection is revisited with decision-
  data recording.

## Timeline Considerations

- Largest item in this batch (effort L). Depends on PRD-004 only when
  reproduction includes BGM content; a CLI-only reproduce without BGM can
  proceed independently.
- Suggested phasing: v1 = CLI command with dry-run + per-locale status;
  fast follow = decision-data recording and BGM reproduction; later = ASC
  plan integration and Studio action.
