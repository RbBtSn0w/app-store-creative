---
name: app-store-creative-publisher
description: Plan, execute, recover, and audit human-approved App Store screenshot and App Preview uploads through the official ASC plugin. Use only after local validation, promotion, design approval, and a separate upload approval are present, or when reconciling a partial media upload with live App Store Connect state.
---

# App Store Creative Publisher

Publish approved media only. Use the official ASC plugin for current authentication, ID resolution, screenshot, and video-preview operations; do not duplicate its connector or API implementation.

## Publish

1. Refuse CI environments and unattended execution.
2. Read [asc-recovery.md](references/asc-recovery.md), the promoted release manifest, validator evidence, and both approval records.
3. Resolve the live app, version, localization, display-type, and preview-set IDs with ASC.
4. Generate an upload plan and compare it with a fresh remote read.
5. Require the separate upload approval to match the exact plan/input manifest.
6. Run the engine's `upload` gate to verify approval and materialize the dry-run intent; it does not mutate ASC.
7. Execute the approved operations through the official ASC plugin only.
8. Run the engine's local-integrity `audit`, then perform a separate fresh ASC read for remote order and completeness. Report local intent, successful writes, failures, local integrity, and remote truth separately.

```sh
python3 <plugin-root>/scripts/app_store_creative.py upload-plan --repo <repo> --release <version> --app <app-id> --version-id <version-id> --output <plan-file>
python3 <plugin-root>/scripts/app_store_creative.py approve --repo <repo> --release <version> --stage upload --approved-by <identity> --input-manifest <plan-file> --confirm APPROVE
python3 <plugin-root>/scripts/app_store_creative.py upload --repo <repo> --release <version> --plan <plan-file> --confirm-approved UPLOAD
python3 <plugin-root>/scripts/app_store_creative.py audit --repo <repo> --release <release.json> --app <app-id> --version-id <version-id>
```

The `audit` command is deliberately local-only and returns
`remote_verified: false`. Never treat it as ASC evidence; the official ASC
plugin read is the remote audit.

Never submit the app version for review, change release options, or delete an old remote set before verified replacements are available. Stop when live ambiguity could target the wrong version or localization.
