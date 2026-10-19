# Sprint 001: PRD Batch Implementation

**Dates:** 2026-10-20 — 2026-11-02 | **Team:** 1 developer (rbbtsn0w)
**Sprint Goal:** Close the measurement→production loop: fix the macOS GPU
export invariant, register standalone BGM compose into the lifecycle, and
ship `ppo reproduce` v1 (CLI-only) so a winning variant can be reproduced
into provenance-tracked deliveries with one command.

## Capacity

| Person | Available Days | Allocation | Notes |
|--------|---------------|------------|-------|
| rbbtsn0w | 10 of 10 | 7.5 pts (1 pt = 1 effective day, planned at 75%) | Solo maintainer; interrupts expected |
| **Total** | **10** | **7.5 pts** | |

Planning at 75% per the 70–80% buffer guideline. No PTO or external meeting
calendar is connected; capacity reflects an interrupt reserve of 2.5 days.

## Sprint Backlog

| Priority | Item | Estimate | Owner | Dependencies |
|----------|------|----------|-------|--------------|
| P0 | PRD-003: macOS GPU export invariant fix + platform tests | 1 pt | rbbtsn0w | None |
| P0 | PRD-004: standalone BGM compose lifecycle registration | 1 pt | rbbtsn0w | None (PRD-006 conditional gate) |
| P0 | PRD-006 v1: PPO winner variant → production reproduction | 5.5 pts | rbbtsn0w | R1a/R1b subtasks below; PRD-004 only if BGM content included |
| Stretch | PRD-007: provenance audit report export (CLI, Markdown) | 1.5 pts | rbbtsn0w | PRD-004 complete (so BGM receipts appear in reports) |
| Deferred | PRD-005: Studio example project onboarding | 3–4 pts (M) | next sprint | Quality-ordering after 003/004 |

**Planned Capacity:** 7.5 pts | **Sprint Load:** 7.5 pts (100% of planned
capacity; stretch is pulled only if core finishes ahead of schedule)

## PRD-006 Subtask Breakdown

PRD-006 is the only L-sized item and carries the sprint goal. It is broken
into six sequenced subtasks so progress is verifiable daily:

| # | Subtask | Estimate | PRD Ref | Notes |
|---|---------|----------|---------|-------|
| 1 | Extend lifecycle record schema with experiment-provenance fields (experiment ID, variant, decision basis) + receipt round-trip test | 1.5 pts | R1a | Explicit schema/contract change; must land before any reproduce code that writes receipts |
| 2 | Implement `ppo reproduce` CLI with explicit `--variant` (required, no auto-selection) | 2 pts | R1 | Production entry point is `production_lifecycle.produce()`; no new bulk path |
| 3 | Wire per-treatment storage namespace strategy (reuse `derive_treatment_config` layout) + namespace landing test | 1 pt | R1b | Treatments remain namespaced; no shared-workspace mixing |
| 4 | Dry-run mode: human-readable output (provenance header, locale-grouped plan, summary counts) + `--json` | 0.5 pt | R2 | Default output is for release-manager review; no storage mutation |
| 5 | Per-locale status reporting with partial-failure semantics | 0.5 pt | R3 | Per-locale status; run does not mark complete on any failure |
| 6 | Integration test: fixture experiment → reproduce → assert provenance chain end to end | (included in subtasks 1–3) | R1 | Validates the sprint goal statement |

Subtask sequencing matters: 1 is a contract change that gates 2–5; 3 depends
on 2's CLI skeleton; 4 and 5 are additive to 2 and can be interleaved. If the
sprint runs behind, subtask 5 (per-locale status granularity) can degrade to
"run-level failure with per-locale output logged" without losing the goal,
and subtask 4's human-readable format can simplify to a flat list — both
degradations are documented fallbacks, not silent scope cuts.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| PRD-006 schema change (R1a) touches the lifecycle kernel, which has known cross-module coupling | Delays subtasks 2–5; may surface hidden record-store dependencies | Time-box subtask 1 to 2 days; if the schema change expands beyond provenance fields, stop and split into a separate contract PR rather than blocking the sprint |
| PRD-006 scope is underestimated (engineering review flagged the decision-data gap late) | Sprint goal at risk if reproduce grows beyond CLI-only | v1 boundary is explicit `--variant`, no decision recording, no BGM, no Studio action; any addition goes to the next sprint backlog |
| Solo maintainer interrupt (production issue, urgent review) | Capacity drops below the 7.5-pt plan | Stretch (PRD-007) is the designated cut; if interrupts exceed 2 days, PRD-006 subtasks 4–5 carry over and the sprint goal narrows to "schema + CLI core landed" |
| PRD-003 GPU fix changes export behavior in unexpected ways on non-`.app` Chrome | Blocks confidence in the fix; may require rollback | Acceptance tests cover both bundle and bare paths before merge; a manual macOS smoke export validates quality before PRD-005 showcase work starts next sprint |

## Definition of Done

- [x] Code self-reviewed against the PRD acceptance criteria (working-tree
      implementation, not yet committed: PRD-003/004/006/007 complete,
      PRD-005 deferred)
- [x] Targeted Python tests passing: `test_chrome_renderer.py`,
      `test_bgm_lifecycle.py`, `test_ppo_experiment.py`,
      `test_artifact_lifecycle.py`, `test_delivery_status.py`,
      `test_delivery_lifecycle.py`, `test_audit_report.py`,
      `test_managed_preview.py`, `test_managed_poster.py`;
      `.github/validate_plugin.py` passes. Full suite blocked only by
      sandbox socket restrictions affecting 12 Studio HTTP tests (known
      environment issue, not introduced by this batch)
- [x] Documentation updated: ADR-003 implementation status (PRD-004),
      sprint plan status. New CLI docs for `ppo reproduce` and
      `audit report` remain open
- [ ] Product sign-off: each PRD's acceptance criteria verified and noted in the PR description
- [x] No dist bundle changes (Studio source unchanged in this batch)

## Key Dates

| Date | Event |
|------|-------|
| 2026-10-20 | Sprint start |
| 2026-10-23 | PRD-003 + PRD-004 targeted complete |
| 2026-10-27 | Mid-sprint check-in: PRD-006 subtask 1 (schema) must be landed; scope check for subtasks 2–5 |
| 2026-10-30 | PRD-006 v1 integration test passing; stretch evaluation |
| 2026-11-02 | Sprint end / demo (recorded end-to-end reproduce) + retro |

## Assumptions

- Sprint length is 2 weeks; no project tracker or calendar is connected, so
  this plan is file-based (no external sprint tooling).
- 1 pt = 1 focused implementation day including tests; documentation and
  review overhead are inside the estimate, not additive.
- PRD-005 is explicitly out of this sprint: at M effort (3–4 pts) it does not
  fit alongside PRD-006's L scope in 7.5 planned pts, and it depends on
  PRD-003's export quality being trustworthy first.

## Sprint Review Status

| Item | Status | Evidence |
|------|--------|----------|
| PRD-003 GPU export invariant | Done | `build_gpu_flag()` platform policy; bundle vs bare-path export tests; 12/12 renderer tests |
| PRD-004 BGM standalone lifecycle | Done | `bgm compose --managed` registers composed media + Swift receipt as producer-evidence; 21/21 BGM lifecycle tests |
| PRD-006 v1 `ppo reproduce` | Done (v1 scope) | `ppo reproduce --experiment --variant [--execute]`; provenance flows from plan to every registered artifact via `production_lifecycle.produce(experiment_provenance=...)`; 21/21 experiment tests, provenance flow test green |
| PRD-007 audit report | Done | `audit report --run-id` Markdown via public query surfaces (`status()`, `delivery_status()`, `list_deliveries()`, `list_publications()`); machine-checkable integrity line; gap-first summary; 21/21 audit tests |
| PRD-005 Studio example project | Deferred to Sprint 002 | Not started; depends on PRD-003 export quality trust |

Remaining sprint-closing work (not blocking the implementation goal):

- [x] New CLI docs: [PPO reproduce](../cli/ppo-reproduce.md) and
      [audit report](../cli/audit-report.md)
- [ ] Full-suite run on a socket-permitted environment (12 Studio HTTP tests
      fail only under sandbox network restrictions)
- [ ] Product sign-off per PRD at review/commit time
