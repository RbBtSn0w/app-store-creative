# PRD-004: BGM Standalone Compose Lifecycle Registration

**Status:** Implemented (Sprint 001)
**Date:** 2026-10-19
**Owner:** rbbtsn0w
**Depends on:** ADR-003 (Apple Loops BGM engine)
**Priority:** P1

## Problem Statement

ADR-003 commits `bgm compose` to register its output as a managed lifecycle
artifact. The managed preview path (`managed_preview.py`) does this correctly.
The standalone CLI path (`app_store_creative.py`) calls `bgm_lifecycle.compose`
and writes the file to disk but never registers the result into the artifact
lifecycle — no managed attempt, no receipt, no inventory entry. The result is
an orphan file that the provenance chain cannot see.

Users affected: anyone composing BGM via the standalone CLI instead of a
managed preview run. Frequency: every standalone compose. Cost of not
solving: breaks the provenance-first promise at its core — the product's
differentiator is that every artifact has traceable lineage, and this path
silently produces untraceable artifacts.

## Goals

1. `bgm compose` (standalone) produces the same lifecycle-visible result as
   the managed preview path: a registered artifact with a receipt.
2. A failed registration aborts the compose cleanly: no managed artifact is
   registered and no generated file is left in workspace outputs.
3. The lifecycle record graph remains consistent (no dangling references).

## Non-Goals

- Not changing the BGM DSP/render pipeline (Swift CLI, AAC encoding,
  loudness normalization) — all untouched.
- Not unifying the standalone and managed CLI entry points into one command.
- Not extending BGM to non-Apple-Loops audio sources.

## User Stories

- As a release engineer, I want every `bgm compose` output registered in the
  artifact lifecycle so that I can audit where any preview's music came from.
- As an agent orchestrating a creative pipeline, I want standalone compose
  receipts so that downstream steps can reference the composed audio without
  re-scanning the filesystem.

## Requirements

### Must-Have (P0)

- **R1**: Standalone `bgm compose` creates a managed attempt (or equivalent
  lifecycle record) identical in shape to what `managed_preview.py` creates
  for the same operation.
  - *Acceptance*: Unit test runs standalone compose against a temp repo and
    asserts a receipt + inventory entry exist with a source reference to the
    composed audio file.
- **R2**: If lifecycle registration fails, the standalone compose reports
  failure and does not leave a partially-registered artifact.
  - *Acceptance*: Unit test forces a registration failure (e.g. invalid
    storage root) and asserts the command exits non-zero with no managed
    artifact registered and no generated file left in workspace outputs (a
    user-specified `--output` path outside workspace storage is untouched).

### Nice-to-Have (P1)

- **R3**: The CLI's existing stdout JSON return adds the lifecycle
  artifact/receipt ID so downstream consumers (`ppo`, managed preview) can
  reference it; no new response shape is introduced.
  - *Acceptance*: Standalone compose stdout JSON contains the lifecycle ID;
    the ID resolves via the existing inventory query.

### Future Considerations (P2)

- Fold standalone compose into the same dispatch layer as managed preview so
  both share one registration codepath, eliminating the divergence class of
  bug.

## Success Metrics

- **Leading**: The new unit tests pass: standalone compose registers a
  receipt, and forced registration failure exits non-zero with no workspace
  output.
- **Lagging**: Every standalone compose recorded in the lifecycle inventory
  has a matching receipt (spot-check via inventory/history commands); the
  ADR-003 implementation-status doc is updated to "Done" with the test as
  evidence.

## Open Questions

- *(engineering, resolved)* `bgm_lifecycle.compose` returns the parsed Swift
  receipt (attempts, LUFS, peak, frames, duration, output path, elapsed) —
  sufficient metadata for receipt generation.
- *(engineering, resolved)* The CLI stdout is already JSON; the lifecycle ID
  is added to the existing return dict (R3), no new shape.

## Timeline Considerations

- Small, contained change in the CLI dispatch plus tests. Should land before
  or together with PRD-006, since the winner-variant flow may reference BGM
  receipts.
