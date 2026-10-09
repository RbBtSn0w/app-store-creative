---
name: app-store-creative-publisher
description: Plan, execute, recover, and audit human-approved App Store screenshot and App Preview uploads through the official ASC plugin. Use only after local validation, immutable sealing, design approval, and a separate upload approval are present, or when reconciling a partial media upload with live App Store Connect state.
---

# App Store Creative Publisher

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


Publish approved media only. Use the official ASC plugin for current authentication, ID resolution, screenshot, and video-preview operations; do not duplicate its connector or API implementation.

## Managed Publication Handoff

Read [the lifecycle contract](../app-store-creative/references/lifecycle-contract.md). New work uses a sealed delivery, a publication plan with actual Git retrieval evidence, a separate exact-plan upload approval, and `publication export --confirm`. Do not use `.creative/asc-handoff.json` or a free-floating `publish` confirmation as approval evidence.

Resolve live ASC resource IDs and reconcile the exported plan with fresh ASC state before external mutation. Execute only the human-approved plan through the official ASC plugin. Normalize actual executor observations into the lifecycle contract and use `publication observe`/`publication status`; keep upload, processing, playable video, and decoded poster gates separate. `publication normalize-asc-preview` converts supported official preview-list responses using an exact executor scope. It does not execute uploads, establish app/version/localization relationships, prove playback, or decode a poster. Unsupported response shapes must be reported, never inferred. Never submit a version for review.

## Execution and Recovery

Read [asc-recovery.md](references/asc-recovery.md) before reconciling a partial upload. Refuse CI or unattended external execution. Resolve live app, version, localization, display type, and preview set IDs. Compare the approved publication plan with fresh remote state and use the official ASC plugin to execute only those authorized operations. Register bound observations through the managed publication commands and retain failures or missing evidence explicitly.

Never submit the app version for review, change release options, or delete an old remote set before verified replacements are available. Stop when live ambiguity could target the wrong version or localization.

## Preview observation normalization

```sh
python3 <runtime-root>/scripts/app_store_creative.py publication normalize-asc-preview --repo <repo> --id <publication-id> --response <asc-preview-list.json> --scope <executor-scope.json>
```

The scope requires exactly `target`, `artifact_id`, `localization_id`, `remote_id`,
`observed_at`, and `evidence_reference`. The target must equal the publication
plan; the artifact must be its selected preview. The ASC executor must verify
the app/version/localization relationship before supplying scope. References
must be sanitized identities, and observation time must be timezone-aware.
Normalization returns bound observations without remote writes. Register each
observation through `publication observe --observation <observation.json> --evidence <asc-preview-list.json>`.
Normalization hashes the original response bytes into `evidence_sha256`; retain
that exact file under the executor evidence reference. Missing or changed bytes
are refused at registration. The hash does not authenticate the executor or
guarantee permanent retrieval. Normalization alone does not update
publication readiness. A processing state of COMPLETE does not prove playback
or poster loading, and zero poster dimensions remain a separate failure.


## Original receipt custody

After registering an observation, use the returned observation ID to retain the exact receipt bytes. Do not substitute normalized JSON, a summary, a URL, or another response. Then persist the retained evidence using a host-local configured backend name and export the publication locator.

```sh
python3 <runtime-root>/scripts/app_store_creative.py publication retain-evidence --repo <repo> --observation-id <observation-id> --evidence <original-receipt> --actor <executor-id>
python3 <runtime-root>/scripts/app_store_creative.py publication persist-evidence --repo <repo> --evidence-id <returned-evidence-id> --backend <configured-backend-name>
python3 <runtime-root>/scripts/app_store_creative.py publication export --repo <repo> --id <publication-id> --confirm EXPORT
```

Keep receipt bytes and backend access paths private. Exported evidence locators contain immutable version identities, hashes and observation scope; they do not contain original response bodies. Git actions require existing user authorization. Obtain a trusted locator hash from the reviewed exact Git commit, then verify independent retrieval in a clean directory:

```sh
python3 <runtime-root>/scripts/app_store_creative.py archive retrieve-evidence --path <committed-locator.json> --expected-sha256 <trusted-locator-sha256> --backend-root <private-backend-root> --destination <new-receipt-file>
```

This consumer does not require the production workspace or configuration. Hashing an untrusted locator does not establish trust. A successful readback proves byte consistency at that time, not backend permanence, executor authenticity, upload authorization or remote media acceptance. Missing versions and changed bytes must remain failures.

If a request result is unknown, inspect existing records before retrying. Never repeat ASC uploads to repair missing local evidence. An unfinished evidence producer cannot be persisted or exported. Use explicit expired-lease recovery, preserve original work, and create a new retention attempt; do not fabricate a successful outcome for interrupted work.
