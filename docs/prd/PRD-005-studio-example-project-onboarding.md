# PRD-005: Studio Example Project Onboarding

**Status:** Draft — pending triage review
**Date:** 2026-10-19
**Owner:** rbbtsn0w
**Depends on:** Studio app (`plugins/app-store-creative/studio/`)
**Priority:** P2

## Problem Statement

The Studio web app launches into an empty state with no path to a working
result without completing the full configuration flow (storage roots, card
data, target device). Competitors like AppMockUp offer a visible result within
30 seconds of opening the tool. Our onboarding friction is a documented
weakness from the competitive analysis, and it disproportionately hurts
first-time and evaluation users — the exact segment that decides whether to
adopt the tool.

Users affected: first-time users, evaluators, and anyone demoing the tool.
Frequency: once per user (first impression), but it gates all later usage.
Cost of not solving: evaluation users churn before seeing the 3D canvas and
export quality that are the product's actual differentiators.

## Goals

1. A new user can see a fully-populated 3D canvas with a complete card arc
   (Hero / Mechanism / Depth / Ecosystem / CTA) within 60 seconds of opening
   Studio, with zero configuration. (Hypothesis; measured via a small
   usability pilot, not telemetry.)
2. The example project demonstrates the export pipeline end to end through
   a dedicated, pre-provisioned sample workspace — a working export produces
   a valid PNG without the user configuring storage.
3. Example state is clearly labeled in the UI and strictly isolated from
   real workspaces; sample exports contain no "sample" markings.

## Non-Goals

- Not building a tutorial, tooltip tour, or interactive walkthrough.
- Not changing the existing configuration flow for real projects.
- Not adding a template gallery with multiple examples (single example only
  for v1).
- Not modifying the 3D canvas or export engine.

## User Stories

- As a first-time user, I want to load an example project with one click so
  that I can see what the tool produces before investing in setup.
- As an evaluator comparing tools, I want the example to be exportable so
  that I can test the full pipeline without configuring storage (the sample
  uses its own pre-provisioned workspace).
- As a demo presenter, I want example data clearly labeled so that I don't
  confuse it with real workspace data in front of stakeholders.

## Requirements

### Must-Have (P0)

- **R1**: Studio empty state offers a "Load example project" action. Loading
  auto-provisions a dedicated sample workspace through the existing managed
  pipeline (clearly labeled) — the user never configures storage.
  - *Acceptance*: Clicking it populates the canvas with a complete card arc
    (Hero / Mechanism / Depth / Ecosystem / CTA) for one device target; the
    sample workspace exists and is labeled.
- **R2**: The loaded example supports the export flow end to end through the
  existing managed pipeline (save + `If-Match` semantics), writing only into
  the sample workspace.
  - *Acceptance*: Export from example state produces a valid PNG at the
    target's physical dimensions; no artifact appears in any real workspace.
- **R3**: Example state is labeled in the UI only — a persistent header-area
  banner plus badge, visible in both workspace modes, never rendered into
  exported pixels.
  - *Acceptance*: Both workspace modes show the label after loading; the
    exported PNG contains no sample marking.
- **R4**: The user can exit example mode and remove the sample workspace.
  - *Acceptance*: A visible exit/cleanup action removes the sample workspace
    without touching real workspaces.

### Future Considerations (P2)

- Multiple example projects targeting different verticals (game, utility,
  social).
- BGM demo track on the example preview video, skipped gracefully when the
  Swift BGM binary is absent.
- Example projects as an automated smoke-test fixture for Studio E2E tests.

## Success Metrics

- **Leading**: In a usability pilot (n ≥ 5 first-time users), time-to-first-
  canvas is under 60 seconds for every participant. This product has no
  telemetry, so this is measured manually.
- **Lagging**: Pilot participants reach export without assistance; the
  sample workspace contains no artifacts outside the sample namespace
  (verified by inventory inspection after each pilot session).

## Open Questions

- *(design, resolved)* The example uses a fictional app brand — no real-
  customer licensing or privacy exposure.
- *(design, resolved)* Label = persistent header banner + badge; no canvas
  watermark (keeps exported pixels clean).
- *(engineering, resolved)* Example content ships as a bundled asset (Studio
  static assets already build into the runtime `dist` bundle); the sample
  workspace is provisioned server-side through the existing managed pipeline.
- *(engineering, resolved)* Effort is M, not S: sample-workspace provisioning
  and the `If-Match` save/export flow are included, so this is not
  frontend-only.

## Timeline Considerations

- Includes frontend work plus server-side sample-workspace provisioning;
  effort M. Design decisions above are resolved.
- Should follow, not precede, PRD-003 and PRD-004 — a quality-ordering
  dependency (the example showcases the fixed export and provenance), not a
  code dependency.

## Validation Triad

Per repo guidelines, any implementation must pass:

```bash
cd plugins/app-store-creative/studio
npm test && npx tsc --noEmit && npm run build
```

And the dist bundle must be synced.
