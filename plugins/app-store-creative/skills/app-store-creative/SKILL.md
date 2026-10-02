---
name: app-store-creative
description: Orchestrate an evidence-gated App Store screenshot and App Preview release from planning through real-UI capture, Figma composition, video production, validation, two explicit approvals, promotion, upload, and remote audit. Use for a complete creative release, resuming a run, coordinating specialist agents, or determining whether App Store media is ready to upload.
---

# App Store Creative

Coordinate specialists through the repository plan. Keep product pixels real, artifacts traceable, and App Store Connect writes human-approved.

## Preflight

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime` from this skill's installed path. Runtime resources live inside the declared main skill payload so ADG installs them. Use Python 3.10 or newer (prefer the Homebrew interpreter on macOS). Before relying on a command, inspect its current interface:

```sh
python3 <runtime-root>/scripts/app_store_creative.py --help
python3 <runtime-root>/scripts/app_store_creative.py doctor --repo <repo>
```

Run `doctor` against the installed plugin before starting. Missing scripts, schemas,
templates, or Studio files indicate an incomplete distribution; use a complete
local package or report the installation defect. Do not infer readiness from skills alone.

Require the official Figma and ASC plugins for their respective external systems. Do not recreate their connectors, authentication, or API schemas locally.

## Agent-Native Workflow (v2.0 Recommended)

For fast, deterministic, local-first iteration without Figma dependencies:

1. **Declare**: Read or create `creative.config.json` with project info, device targets, visual theme, and cards.
2. **Preview (Dev)**: Start the local studio on `localhost:3100` (`app_store_creative.py dev`) for instant human & Agent visual grounding.
3. **Export**: Run `app_store_creative.py export` (add `--with-video` for App Preview videos) to generate 1:1 store-accurate, 24-bit RGB PNGs via headless Chrome.
4. **Verify**: Run `app_store_creative.py verify` to check zero-network compliance and generate `.creative/release-lock.json`.
5. **Handoff**: Inspect `app_store_creative.py publish`; use `--confirm` to write `.creative/asc-handoff.json`. This prepares local artifacts only and grants no upload approval. Delegate uploads and remote audits to the official ASC plugin after separate human design and upload approvals.

```sh
python3 <runtime-root>/scripts/app_store_creative.py dev
python3 <runtime-root>/scripts/app_store_creative.py export --with-video
python3 <runtime-root>/scripts/app_store_creative.py verify
python3 <runtime-root>/scripts/app_store_creative.py publish --confirm
```

## Multi-Agent Manifest Workflow (Legacy v1 Contract)

1. Initialize only when the repository has not adopted the workflow; `init` refuses to overwrite existing files.
2. Create a run and treat its generated plan as the task graph and state authority.
3. Dispatch capture, design, preview, validation, and publishing work to the matching specialist skills.
4. Resume from `status`; do not infer completion from files merely existing.
5. Require a design approval before promotion and a separate upload approval before any App Store Connect mutation.
6. Run `verify` before approval, promotion, and upload. Run `audit` after upload.

When a follow-up changes source inputs for an unpromoted task, read [iteration-contract.md](references/iteration-contract.md), invalidate that task, and re-run only the proved-dependent work. Preserve unaffected task evidence. Create a new run instead when release-manifest task fields changed or any affected task was promoted.

```sh
python3 <runtime-root>/scripts/app_store_creative.py init --repo <repo>
python3 <runtime-root>/scripts/app_store_creative.py plan --repo <repo> --release <version> --run-id <run-id>
python3 <runtime-root>/scripts/app_store_creative.py status --repo <repo> --run-id <run-id>
python3 <runtime-root>/scripts/app_store_creative.py verify --repo <repo> --release <version> --run-id <run-id>
```

Never upload from CI. Never submit an app version for review. Report local validation, human approvals, upload outcome, and fresh ASC state as separate facts.

Read [workflow-contract.md](references/workflow-contract.md) before starting or resuming a multi-agent release. Read [agent-handoff.md](references/agent-handoff.md) when claiming or completing planned tasks.
