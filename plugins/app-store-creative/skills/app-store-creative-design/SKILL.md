---
name: app-store-creative-design
description: Compose and localize App Store screenshot frames in Figma using real captured product UI, release copy, and repository-defined dimensions and scene order. Use when creating or updating editable screenshot layouts, themes, safe areas, localized typography, product framing, or design-review exports for an App Store creative run.
---

# App Store Creative Design

Use the official Figma plugin as the editable design system. Before any Figma operation, load its mandatory `figma-use` skill; load its generation skill when creating or materially restructuring designs. Never copy Figma connector code or authentication into this plugin.

## Compose

1. Read the plan, manifest, copy source, raw-capture receipt, and [figma-design-contract.md](references/figma-design-contract.md).
2. Claim the design task.
3. Update deterministic source-asset nodes with raw captures.
4. Compose every required locale, scene, device class, and release theme without editing pixels inside the captured UI region.
5. Keep text editable. Enforce safe areas, contrast, line limits, locale fit, and consistent product geometry.
6. Export review artifacts at the manifest's exact size and color requirements.
7. Record the Figma file/key, page and frame identifiers, input hashes, export mapping, and visual-review notes in the receipt; complete the task.

```sh
python3 <plugin-root>/scripts/app_store_creative.py claim --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id>
python3 <plugin-root>/scripts/app_store_creative.py complete --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id> --receipt <receipt-file>
```

Do not promote exports yourself. The orchestrator may request design approval only after validation succeeds; that approval is not upload approval. The approval confirmation token is `APPROVE`.

For a follow-up that changes copy or presentation only, update only the Figma frames selected by the source map. If a product capture hash changes, export every frame that references it. For `source-map-v1`, complete with a `design` receipt containing the required capture hashes, output binding, and Figma node IDs; see the orchestrator's [iteration contract](../app-store-creative/references/iteration-contract.md).
