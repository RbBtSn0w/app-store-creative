---
name: app-store-creative-validator
description: Validate App Store screenshot and App Preview artifacts, receipts, manifests, visual acceptance evidence, and upload readiness without mutating App Store Connect. Use before design approval, promotion, upload approval, or publishing, and when diagnosing missing locales, bad dimensions, alpha, color, naming, ordering, codec, duration, stale hashes, or incomplete provenance.
---

# App Store Creative Validator

Produce read-only evidence. A passing validator is necessary but never substitutes for either human approval.

## Validate

1. Read [validation.md](references/validation.md), the run plan, receipts, release manifest, and approval records.
2. Run the engine verifier.
3. Validate screenshots for exact set, order, dimensions, encoding, color space, alpha policy, hashes, and unexpected files.
4. Validate previews with `ffprobe`; inspect the acceptance snapshot because ASC video previews have no equivalent local `asc validate` command.
5. Use the official ASC plugin to construct or inspect a dry-run upload plan. Do not perform a write.
6. Visually inspect product authenticity, clipping, seams, overlays, localized overflow, misleading composition, and preview continuity.
7. Report blocking failures separately from warnings and state which boundary remains unproven.

```sh
python3 <plugin-root>/scripts/app_store_creative.py verify --repo <repo> --release <version> --run-id <run-id>
python3 <plugin-root>/scripts/app_store_creative.py upload-plan --repo <repo> --release <version> --app <app-id> --version-id <version-id> --output <plan-file>
```

On a resumed run, verify the engine-enforced `source-map-v1` receipt and [iteration contract](../app-store-creative/references/iteration-contract.md) as well as the media. Require invalidated tasks to be recompleted and regenerate any upload plan bound to an archived receipt; matching names and dimensions do not prove that an export uses current inputs. Do not alter artifacts to make validation pass. Return defects to their owning capture, design, or preview task.
