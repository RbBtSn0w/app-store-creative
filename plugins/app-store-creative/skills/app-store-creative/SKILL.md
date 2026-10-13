---
name: app-store-creative
description: Orchestrate an evidence-gated App Store screenshot and App Preview release from planning through real-UI capture, Figma composition, video production, validation, two explicit approvals, immutable sealing, ASC handoff, and remote audit. Use for a complete creative release, resuming a run, coordinating specialist agents, or determining whether App Store media is ready to upload.
---

# App Store Creative

Coordinate specialists through the repository plan. Keep product pixels real, artifacts traceable, and App Store Connect writes human-approved.

## Preflight

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime` from this skill's installed path. Runtime resources live inside the declared main skill payload so ADG installs them. Use Python 3.11 or newer (prefer the Homebrew interpreter on macOS). Before relying on a command, inspect its current interface:

```sh
python3 <runtime-root>/scripts/app_store_creative.py --help
python3 <runtime-root>/scripts/app_store_creative.py storage inspect --repo <repo>
```

Inspect the consuming project through the installed managed CLI before starting. Validate the complete package, including scripts, schemas, templates, and Studio files. Missing payloads indicate an incomplete distribution; report the installation defect. Do not infer readiness from skills alone.

Require the official Figma and ASC plugins for their respective external systems. Do not recreate their connectors, authentication, or API schemas locally.

## Managed Artifact Workflow

Read [lifecycle-contract.md](references/lifecycle-contract.md) before producing or resuming materials. CLI, Studio, and agents use the same immutable run, attempt, artifact, candidate, approval, delivery, publication, and observation records.

1. Declare `creative.config.json`, including the stable project identity and storage roots. Inspect `storage inspect` and `storage git-policy`; do not silently edit Git rules or use arbitrary output directories.
2. Import real UI sources with `input import`, or register producer inputs and outputs against an active leased attempt. Keep app-specific journeys in the consuming project. Use the packaged [Preview Producer](../app-store-preview-producer/SKILL.md) for capture and timeline execution; register its media and evidence through the lifecycle core.
3. Use Studio or `export --repo <repo>` (`--with-video` when required). Managed export records independent attempts, provenance, candidates, and validation. Retain failure reasons and partial artifacts; never reuse an earlier successful result as proof of the current attempt.
4. Validate the exact candidate. Obtain explicit human design approval, record its authorization reference, and seal an immutable delivery. An agent may not invent approval evidence.
5. Review the proposed Git rules and archive changes. Stage, commit, push, or create a PR only with user authorization. Verify retrieval from the intended commit and configured remote when remote availability is required.
6. Create a publication plan for explicit ASC app/version/platform IDs. Obtain a separate upload approval bound to this exact plan. Export the managed handoff for the official ASC plugin.
7. Use `publication normalize-asc-preview` for official ASC Preview list responses with an independently resolved executor scope. Record bound executor observations and inspect `publication status`. Upload, processing, playback, and poster readiness are separate gates; missing, stale, or contradictory evidence must not become success.
8. Read `storage artifact-policy` before maintenance and `storage media-budget` for retained payload estimates (optionally `--candidate-id`). Unknown archives or remote usage must remain unknown. Use `inventory`, retirement, and planned maintenance for retention. Moving configured roots requires `storage plan-relocate`, preparation, and explicit switching; never reinterpret old records or delete a whole custom directory.

```sh
python3 <runtime-root>/scripts/app_store_creative.py storage inspect --repo <repo>
python3 <runtime-root>/scripts/app_store_creative.py export --repo <repo>
python3 <runtime-root>/scripts/app_store_creative.py candidate validate --repo <repo> --id <candidate-id>
python3 <runtime-root>/scripts/app_store_creative.py inventory --repo <repo>
python3 <runtime-root>/scripts/app_store_creative.py history verify --repo <repo>
python3 <runtime-root>/scripts/app_store_creative.py candidate review --repo <repo> --id <candidate-id>
python3 <runtime-root>/scripts/app_store_creative.py publication list --repo <repo>
```

Use candidate/delivery/publication commands as the only validation and publication workflow. Standalone `verify`/`publish` and legacy task commands are removed. Existing unmanaged files are preserved but are not accepted as lifecycle authority.

Never upload from CI or submit a version for review. The official ASC plugin performs external execution and fresh remote reads; Creative prepares, binds, and evaluates evidence. Report completed gates and remaining gaps separately.


## Release input review

Before producing a release candidate for approval, enable `studio.requireExportEvidence` in the reviewed project configuration. Use the strict input and rendering evidence checks for every target and locale. A permissive exploratory export does not establish that localized capture assignments or rendering evidence have been reviewed.

For nondefault locales, assign real localized captures or record an explicit reviewed `inheritDefault` decision. Do not mark UI localization complete from translated headlines. Never reuse already composed store images as raw captures. If required inputs are unavailable, report the exact blocked locale/scene and retain exploratory attempts separately from approved delivery revisions.
