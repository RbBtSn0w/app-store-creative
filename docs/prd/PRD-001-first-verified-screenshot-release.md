# PRD-001: First Verified Screenshot Release

**Status:** Draft for product review; implementation is not authorized by this document.
**Date:** 2026-10-02
**Product:** App Store Creative
**Owner:** rbbtsn0w
**Source baseline:** Local checkout `6775339`; competitive research from this conversation dated 2026-10-02.

## 1. Problem Statement

Independent Apple developers with real application screenshots need to turn those captures into an editable, correctly sized screenshot set without first learning release manifests or assembling a design toolchain. The current Studio provides previews and text editing, but its configuration-first setup and separate editing, saving, exporting, and validation steps can leave users uncertain whether exported files contain their latest changes. Free competitors already provide useful editing workflows, so first-use friction can prevent users from reaching Creative's repeatable release and validation benefits.

This is a product hypothesis grounded in source inspection and competitor feedback, not a measured onboarding funnel or a completed usability study.

## 2. Evidence and Prior Art

| Observation | Evidence | Implication |
|---|---|---|
| Agent-driven screenshot creation and connected canvases already exist. | [Parth product](https://www.parthjadhav.com/products/app-store-screenshots), [editor template](https://github.com/ParthJadhav/app-store-screenshots/blob/main/skills/app-store-screenshots/template/README.md) | Agent support and panorama alone are not differentiators. |
| Parth's current source includes RGB PNG encoding and export image readiness checks. | [Export renderer](https://github.com/ParthJadhav/app-store-screenshots/blob/main/skills/app-store-screenshots/template/src/lib/export-render.ts) | Reliable exports are a competitive baseline, not an exclusive claim. |
| AppScreen provides immediate browser access and localized assets. | [Live product](https://yuzu-hub.github.io/appscreen/) | Time to first useful output matters. |
| Users report alpha-channel, CJK wrapping, and language-layout problems. | AppScreen [#24](https://github.com/YUZU-Hub/appscreen/issues/24), [#46](https://github.com/YUZU-Hub/appscreen/issues/46), [#36](https://github.com/YUZU-Hub/appscreen/issues/36) | Localization and output correctness need explicit acceptance criteria. Reports are not universal failure rates. |
| Users want help placing multilingual assets into ASC. | AppScreen [#25](https://github.com/YUZU-Hub/appscreen/issues/25) | Keep a path from verified assets to downstream publishing. |
| AppScreen automation and panorama are proposed in an open community PR. | [PR #37](https://github.com/YUZU-Hub/appscreen/pull/37) | Monitor automation convergence; do not count unmerged work as shipped. |

Current local implementation references:

- `plugins/app-store-creative/studio/src/App.tsx`: draft editing, explicit saves, and export requests.
- `plugins/app-store-creative/skills/app-store-creative/runtime/scripts/studio_server.py`: configuration persistence and disk-based export invocation.
- `plugins/app-store-creative/skills/app-store-creative/runtime/scripts/validator.py`: declared matrix validation and release evidence.
- `docs/adr/ADR-001-export-proportional-scaling-and-mac-preview-video.md`: accepted proportional scaling decision.

No competitor end-to-end benchmark was run. Repository popularity is not evidence of activation, revenue, or conversion improvement.

## 3. Target Users and Scope Assumptions

**Primary:** Independent Apple developers already working with a supported coding agent and possessing real PNG/JPEG captures.

**Secondary:** Small product teams reviewing and adjusting an agent-prepared screenshot project in Studio.

The initial workflow assumes Python and a supported Chromium browser are installed. Environment failures must be explained before editing begins. Fresh-machine installation time is measured separately from the core task.

The v1 reference task is six cards, two locales (`en-US`, `zh-Hans`), and two existing targets (`iphone_6_9`, `mac_16_10`): 24 declared outputs. Phone and desktop use appropriate real source captures; phone UI is not relabeled as a desktop application. The user may choose fewer cards or a single locale/target.

Existing target and locale configurations remain usable. This reference matrix defines guaranteed new-flow coverage, not a removal of existing capabilities.

## 4. Goals

1. **User outcome:** At least 8 of 10 eligible pilot participants complete the reference task without facilitator rescue; stretch target is 9 of 10.
2. **User outcome:** Median time from starting a ready-environment project to verified output is at most 15 minutes and at least 30% below the measured current-workflow baseline; stretch is 10 minutes and 50% below baseline.
3. **Correctness outcome:** Every successful reference run includes all 24 required outputs, correct ordering and dimensions, no alpha channel, and no known missing-image, clipped-text, or stale-input failure in the acceptance fixtures.
4. **Trust outcome:** Every induced save, asset-load, render, and validation failure produces an actionable status and preserves recoverable user work; no failed run is labeled verified.

All numerical targets are explicit planning hypotheses. No baseline or pilot result exists yet.

## 5. Non-Goals

1. **Remote publishing in this increment:** ASC upload, replacement, authorization, and remote processing remain owned by the existing ASC workflow.
2. **Application capture automation or new video functionality:** Users bring real captures; recording and preview production are a later phase.
3. **A general-purpose design editor:** Freeform vector tools, template marketplaces, and true 3D modeling would expand scope beyond the first-release problem.
4. **New device categories or a hosted service:** Use existing targets and the local runtime; no account system, cloud storage, or billing work.
5. **An embedded translation service or conversion promise:** Use the existing agent for copy assistance; semantic approval stays human. Do not claim improved store conversion without experiments.

## 6. User Stories

### Independent developer

- As an independent developer, I want to start a project from my real captures so that I can see useful cards without hand-authoring a manifest.
- As an independent developer, I want to assign captures to the intended card, language, and device family so that another locale or platform does not accidentally reuse the wrong UI.
- As an independent developer, I want to edit copy and select a supported composition so that each screenshot communicates a clear outcome.
- As an independent developer, I want exported files to match the version I reviewed so that I can trust the result.
- As an independent developer, I want failed imports and exports to identify the affected item so that I can fix it without restarting the project.

### Reviewer and returning user

- As a product reviewer, I want to inspect every required language and target so that a successful export does not conceal missing or clipped content.
- As a returning developer, I want to reopen the saved project with the same assets and ordering so that I can continue after closing Studio.
- As a returning developer working alongside an agent, I want a conflicting save to preserve both versions so that newer work is not silently overwritten.

## 7. Intended Workflow

1. Start Studio and check required local capabilities.
2. Create a project or open an existing configuration.
3. Choose supported targets and locales; import and assign real captures.
4. Generate or enter copy; preview and adjust each required composition.
5. Save the reviewed state and export either a selected subset or the entire declared matrix.
6. Review output and validation findings; repair and retry failed items.
7. When the entire declared matrix passes validation, show **Verified locally** and make the existing ASC handoff path discoverable.

Creation gathers the identity fields needed by the existing configuration contract. The agent may prefill project identity, copy, and assignments, but Studio must make them reviewable. Users are not required to inspect hashes, JSON, CLI commands, or internal receipt identifiers to complete this flow.

## 8. Requirements and Acceptance Criteria

### P0: Required for v1

#### P0-1: Start from real captures

Provide a guided empty state and import/assignment flow for PNG and JPEG. Keep assets local and persistent; do not modify source capture bytes. Show thumbnail, card, locale, and device-family assignments before export. Add, reorder, and remove cards through Studio; removal must be reversible or explicitly confirmed.

- Given no project configuration, when the user supplies valid identity fields and captures, then Studio creates a compatible project and shows real images instead of sample screenshots.
- Given a corrupt or unsupported image, when import is attempted, then that item is rejected with a reason and previous assignments remain intact.
- Given duplicate filenames, when both are imported, then neither silently replaces the other.
- Given a phone and a desktop target, when desktop capture assignments are missing, then Studio requests appropriate sources or an explicit suitable composition; it does not silently treat phone pixels as desktop UI.
- Given a saved project, when Studio is closed and reopened, then captures, card identities, and ordering are restored.

**Dependencies:** Existing schema, local asset storage/serving, and supported layouts. Import writes must remain inside the consuming project and preserve user-owned files.

#### P0-2: Review and correct localized compositions

Support editing headline/subheadline, choosing existing layouts/styles, and replacing an assigned capture. Cover English and Simplified Chinese in the reference task. Clearly distinguish explicit localized content from inherited default content. Missing localization may be explicitly accepted as inheritance; it must never be silently represented as translated.

- Given a Chinese locale, when its headline or source image is edited, then the English variant remains unchanged.
- Given an inherited value, when the user reviews that locale, then the inheritance is visible and can be replaced or explicitly accepted.
- Given a long headline in a reference fixture, when previewed or exported, then text wraps within its text region; unresolved clipping or collision with the reserved device region is identified before verification.
- Given phone and desktop targets, when the user switches between them, then both use target-appropriate layouts and preserve their assignments.
- Given a preview and its export for the same target, locale, and saved configuration, then text wrapping, relative placement, and connected cropping match at normalized scale.

**Dependencies:** Existing proportional-scaling ADR. Device-family-specific choices may require a backward-compatible configuration extension; review it before implementation. Unconfigured choices retain existing behavior.

#### P0-3: Save and export the reviewed version

Bind an export to a saved configuration snapshot and the actual source asset versions. Export either saves the reviewed draft successfully first or explicitly blocks until it is saved. A failed save cannot fall through to export of older disk state. Detect stale saves from another tab or agent and preserve the unsaved draft.

- Given unsaved edits, when export is requested, then the exported result includes those edits after a successful save, or export is blocked with a clear next action.
- Given a disk revision newer than the editor's base revision, when saving, then Studio reports a conflict and does not overwrite the newer version automatically.
- Given edits made while a save is pending, when the older save completes, then later edits remain marked unsaved.
- Given an asset or configuration that changes during export, when results are checked, then they cannot be marked current and verified unless they match the reviewed input versions.
- Given navigation away with unsaved work, when the user leaves, then Studio provides a recoverable draft or an explicit unsaved-work warning.

**Dependencies:** Serialized conditional persistence and render snapshot ownership. Backups alone are not conflict detection. New local mutation endpoints must accept only intended Studio/agent callers, reject cross-origin writes, and validate bounded requests.

#### P0-4: Produce and verify the requested matrix

Expose selected-subset and full-matrix export scopes explicitly. Report progress and affected failures. Reuse the canonical exporter and validator; Studio must not introduce a separate renderer or weaken whole-release validation.

- Given the reference matrix, when full export succeeds, then exactly 24 intended ordered screenshot outputs exist and pass canonical dimension/format/no-alpha checks.
- Given an undecodable image, unavailable required font, or unresolved render readiness failure, when export is requested, then that output fails visibly rather than becoming a verified blank frame.
- Given a selected-subset export with incomplete or stale outputs elsewhere, when it finishes, then Studio labels the subset result accurately and does not mark the whole release verified.
- Given verified outputs, when a configuration or relevant capture changes, then prior evidence remains historical and the current release is shown as requiring fresh verification.
- Given a missing Chromium dependency, when export is attempted, then Studio reports the missing prerequisite without reporting success.

**Dependencies:** Canonical export engine, validator, release evidence, and valid target specifications. Correct dimensions do not imply successful store upload or App Review acceptance.

#### P0-5: Explain failures and completion honestly

Present project-level states that users can act on: **Needs input**, **Unsaved changes**, **Ready to export**, **Exporting**, **Needs attention**, and **Verified locally**. Findings identify card, locale, target, cause, and next action where available. Preserve successfully saved work after failures.

- Given a save or export failure, when the operation ends, then the UI leaves its busy state and offers retry or a specific repair action.
- Given all outputs verified against current inputs, when results are shown, then users can locate the files and inspect the declared matrix.
- Given local verification or handoff preparation, when the summary is shown, then it does not claim uploaded, remotely processed, or approved by Apple.
- Given user text containing markup characters, when saved and rendered, then it remains text and does not execute scripts.

**Dependencies:** Runtime error classification and output metadata. Existing ASC handoff can remain agent-driven in v1; a new publishing interface is not required.

### P1: Follow-ups after the core flow works

| Requirement | Acceptance criteria | Dependency |
|---|---|---|
| P1-1: Editing recovery | Undo/redo restores text, assignments, layout, and order within the session; document the supported history boundary. | Stable edit model |
| P1-2: Wider localization | Fixtures for `ja`, `de-DE`, and `ar-SA` cover CJK wrapping, long text, mixed-direction text, and independent locale choices; unsupported font coverage is actionable. | Font coverage and explicit RTL behavior |
| P1-3: Matrix review | Review every selected card/locale/target combination without exporting; selecting a finding opens its composition. | Canonical preview and findings |
| P1-4: Larger-project responsiveness | For 6 cards × 5 locales × 3 targets, p95 visible edit response is under 250 ms across 30 scripted edits on a recorded reference machine; no frozen interaction exceeds 2 seconds. | Reference hardware and render profiling |

These are follow-ups, not conditions for shipping the tightly scoped v1 reference flow.

### P2: Future considerations

| Direction | Acceptance criterion for a future spec | Preserve now |
|---|---|---|
| Repeat-release rebuilding | Changed inputs identify affected outputs, and stale evidence cannot pass handoff. | Stable identities, source bindings, historical evidence |
| Real recording and preview production | Final media traces to real captures and passes canonical media validation. | Existing recording and video ownership |
| Competitor-project import | Imported assets and assignments are reviewable; unsupported fields are disclosed. | Separate adapters; no competitor schema as canonical state |
| Team review and ASC delivery | Approved versions map to exact assets and independently audited remote results. | Existing approval and publishing boundaries |

P2 requirements require separate scoping and authorization before implementation.

## 9. Success Metrics and Measurement

Use consented pilot observations and local task records. No automatic remote telemetry, screenshot content collection, or new analytics service is required.

| Metric | Definition and method | Success / stretch | Evaluation |
|---|---|---|---|
| First-task completion, leading | Eligible participants producing a complete verified reference matrix without rescue / all eligible participants who start, including abandoned sessions | 8/10 / 9/10 | First 10 pilot participants |
| Time to verified output, leading | Start of ready-environment setup to complete current verification; includes repairs and render time. Report completion rate and failed-session elapsed time alongside completer median. | <=15 min and >=30% baseline reduction / <=10 min and >=50% reduction | Pilot completion |
| Correctness, release gate | Deterministic acceptance-fixture runs with complete, current, properly formatted outputs and matching reviewed content | 100%; no stretch | Every release candidate |
| Failure recovery, release gate | Induced save/render/import failures preserve recoverable work and avoid false success | 100%; no stretch | Every release candidate |
| Repeat-task completion, lagging | Returning pilot participants completing a source/copy update and fresh full verification / all eligible participants starting the follow-up, including abandonment; report invitations, return rate, and sample count separately | >=80% / >=90% | 30-day follow-up |
| Ease of completion, lagging | Post-task 1-5 rating using the same question across baseline and new flow | Median >=4 / >=4.5 | Pilot and 30-day follow-up |

Run the baseline on the current workflow before implementation, using matched assets and participant experience. Counterbalance workflow order where participants use both versions. Record runtime/browser versions, hardware, tasks, failures, intervention, and validation results. Pilot numbers guide decisions; they do not establish population-level retention or market share.

No revenue or competitive win-rate target is proposed without a pricing model and actual purchase/selection data.

## 10. Validation and Release Gates

- Persistence tests: conflicting tabs/agent edits, save failure, edits during save, and reload.
- Import tests: real valid PNG/JPEG, corrupt images, duplicate filenames, and preserved sources.
- Browser integration: empty state through assignment, edit, save, export, inspect, repair, and retry.
- Render acceptance: actual Chromium exports compared with target-specific preview geometry and expected source pixels; checking dimensions alone is insufficient.
- Localization fixtures: independent English/Chinese copy and captures, long strings, explicit inheritance, and empty optional subheadlines.
- Matrix tests: complete reference task, subset export, missing output, changed source, and stale evidence.
- Existing CLI/schema compatibility and packaged-runtime smoke validation remain required for affected components.
- No remote ASC mutation is required to validate this increment.

Release requires P0 acceptance, the recorded reference-matrix check, compatibility checks, and review of pilot findings. If product targets fail, repair or rescope explicitly rather than labeling the targets achieved.

## 11. Open Questions

| Question | Owner | Blocking point | Proposed resolution |
|---|---|---|---|
| Which real phone and desktop captures can be used in repeatable fixtures and consented usability tasks? | Product / design | Before pilot and visual acceptance | Select an authorized product and stable scenes. |
| Which reference machine and Chromium version define timing and render comparisons? | Engineering | Before performance claims | Record one supported macOS environment; publish its limits with results. |
| Can device-family assignments and layout overrides fit the existing contract without breaking consumers? | Engineering | Before schema implementation | Time-box an additive design investigation; keep existing configuration defaults. |
| How much freeform composition is needed beyond current layouts? | Product / design | Non-blocking for v1 | Observe reference-task repairs; expand only if existing layouts prevent completion. |
| Which participating users value repeat release enough to change tools? | Product | Non-blocking for v1 | Conduct follow-up task interviews; use results for phase-two scope. |

No deadline, staffing commitment, approved usability cohort, or performance baseline has been provided.

## 12. Phasing and Timeline Considerations

| Phase | Deliverable | Exit condition |
|---|---|---|
| A: Baseline and contract design | Authorized fixtures, task baseline, additive state proposal | Evidence and implementation boundaries are reviewable |
| B: First verified screenshot flow | P0 import, localized review, consistent save/export, canonical validation, recoverable errors | All P0 acceptance and compatibility checks pass |
| C: Pilot and focused polish | Ten-participant pilot; selected P1 work based on failures | Goals evaluated with sample sizes and unresolved findings |
| D: Continuous release and video | Separate PRDs for repeat builds, existing video integration, and downstream delivery | New scope and dependencies reviewed |

These phases are sequencing recommendations, not calendar estimates. Effort estimates follow phase-A design. A scope addition must remove comparable work or explicitly extend the plan; it must not silently become another v1 P0.

## 13. Product Decision Requested

Review whether the first increment should prioritize **a trustworthy first screenshot set** for existing agent users, using the stated reference task. Then review the P0 boundaries and planning targets. This PRD proposes future behavior; it does not claim these changes are implemented or approve schema changes, release configuration changes, or remote publishing.
