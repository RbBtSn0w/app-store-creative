---
name: app-store-creative-design
description: Compose and localize App Store screenshot frames in Figma using real captured product UI, release copy, and repository-defined dimensions and scene order. Use when creating or updating editable screenshot layouts, themes, safe areas, localized typography, product framing, or design-review exports for an App Store creative run.
---

# App Store Creative Design

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


Use the official Figma plugin as the editable design system. Before any Figma operation, load its mandatory `figma-use` skill; load its generation skill when creating or materially restructuring designs. Never copy Figma connector code or authentication into this plugin.

## Agent-Native Design Workflow (v2.1)

In v2.1, screenshot creative composition is declared directly in `creative.config.json` and previewed live in Localhost Studio (`localhost:3100`).

### 1. The 5-Slide Role Arc

Screenshots are advertisements, not documentation. Each slide must sell one clear user outcome:

1. **Slide 1 (Hero)**: The primary emotional hook or core transformation ("Build Habits That Actually Stick").
2. **Slide 2 (Mechanism / Core Feature)**: The primary daily workflow or delight moment ("Track Daily Progress in One Tap").
3. **Slide 3 (Depth / Proof / Analytics)**: Visual evidence of long-term value ("Insights at a Glance").
4. **Slide 4 (Ecosystem / Integration)**: Platform superpowers ("Right on Your Lock Screen", Widgets, Mac/Watch sync).
5. **Slide 5 (Call to Action / Trust)**: Social proof, privacy commitment, or frictionless onboarding.

### 2. Weak vs. Better Headline Conversion

| Weak (Documents Technical UI) | Better (Sells Outcome / Feeling) |
| :--- | :--- |
| "Daily Habit Tracking App" | "Build Habits That Last" |
| "Interactive Graphs and Charts" | "Insights at a Glance" |
| "Budget Category Selector" | "Master Your Money" |
| "Supports Widgets and StandBy" | "Right on Your Lock Screen" |
| "Workout Log and Timer" | "Crush Every Workout" |
| "AI Chatbot Assistant" | "Supercharge Your Workflow" |

### 3. 18 Curated Visual Style Presets

Apply any of the 18 pre-configured visual style presets under `theme.stylePreset`:

- `liquid_glass`: Aurora glass mesh, titanium natural bezels (AI, utilities, iOS-native)
- `swiss_grid`: Monochrome high-contrast minimalism, flat bezels (Finance, B2B, Dev tools)
- `midnight_glow`: Deep obsidian, neon blue accents, dramatic shadow (Dark mode, power tools)
- `quiet_japandi`: Warm stone neutrals, soft shadows, refined typography (Reading, notes, wellness)
- `bento_keynote`: Slate structure, keynote grid cards, titanium black (Productivity)
- `candy_pop`: Vibrant pastel gradients, high saturation (Social, Gen-Z)
- `neon_athletic`: High-contrast dark, laser green/orange highlights (Fitness, sports)
- `magazine_editorial`: Warm cream editorial styling (Food, coffee, travel)
- *Additional presets: `soft_clay`, `pastel_dream`, `vintage_travel`, `cyber_matrix`, `clean_light`, `dark_contrast`, `ocean_gradient`, `sunset_warmth`, `forest_minimal`, `monochrome_bold`.*

---

## Legacy Multi-Agent Figma Workflow (v1 Contract)

1. Read the plan, manifest, copy source, raw-capture receipt, and [figma-design-contract.md](references/figma-design-contract.md).
2. Claim the design task.
3. Update deterministic source-asset nodes with raw captures.
4. Compose every required locale, scene, device class, and release theme without editing pixels inside the captured UI region.
5. Keep text editable. Enforce safe areas, contrast, line limits, locale fit, and consistent product geometry.
6. Export review artifacts at the manifest's exact size and color requirements.
7. Record the Figma file/key, page and frame identifiers, input hashes, export mapping, and visual-review notes in the receipt; complete the task.

```sh
python3 <runtime-root>/scripts/app_store_creative.py claim --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id>
python3 <runtime-root>/scripts/app_store_creative.py complete --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id> --receipt <receipt-file>
```

Do not promote exports yourself. The orchestrator may request design approval only after validation succeeds; that approval is not upload approval. The approval confirmation token is `APPROVE`.

For a follow-up that changes copy or presentation only, update only the Figma frames selected by the source map. If a product capture hash changes, export every frame that references it. For `source-map-v1`, complete with a `design` receipt containing the required capture hashes, output binding, and Figma node IDs; see the orchestrator's [iteration contract](../app-store-creative/references/iteration-contract.md).
