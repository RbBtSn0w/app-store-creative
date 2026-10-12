---
name: app-store-creative-design
description: Compose and localize App Store screenshot frames in Figma using real captured product UI, release copy, and repository-defined dimensions and scene order. Use when creating or updating editable screenshot layouts, themes, safe areas, localized typography, product framing, or design-review exports for an App Store creative run.
---

# App Store Creative Design

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


When the task uses Figma, use the official Figma plugin as the editable design system. Before any Figma operation, load its mandatory `figma-use` skill; load its generation skill when creating or materially restructuring designs. Never copy Figma connector code or authentication into this plugin.

## Managed Lifecycle Binding

Read the [managed specialist contract](../app-store-creative/references/specialist-lifecycle.md) and apply it to new work. Use leased attempts and registered input/output artifacts; preserve partial failures and their reasons. A producer receipt or file does not grant approval, seal a delivery, or prove remote readiness. Standalone capture/encoding executors still require this explicit registration adapter.

## Configuration-Driven Design Workflow

Screenshot creative composition is declared directly in `creative.config.json` and previewed live in Localhost Studio (`localhost:3100`).

### 1. The 5-Slide Role Arc

Screenshots are advertisements, not documentation. Each slide must sell one clear user outcome:

1. **Slide 1 (Hero)**: The primary emotional hook or core transformation ("Build Habits That Actually Stick").
2. **Slide 2 (Mechanism / Core Feature)**: The primary daily workflow or delight moment ("Track Daily Progress in One Tap").
3. **Slide 3 (Depth / Proof / Analytics)**: Visual evidence of long-term value ("Insights at a Glance").
4. **Slide 4 (Ecosystem / Integration)**: Platform superpowers ("Right on Your Lock Screen", Widgets, Mac/Watch sync).
5. **Slide 5 (Call to Action / Trust)**: Social proof, privacy commitment, or frictionless onboarding.

Connected backgrounds share a full-deck gradient and decoration coordinate space.
Each export is a slice of that background. Headlines and product captures remain
inside their own card; cross-card product or text placement is not supported.
A card with `customBackground` uses its own independent background.
Solid presets remain solid without ambient colored glows.

For Mac captures, select `mac_native_hero` for a centered window under the
headline, or `mac_native_left` / `mac_native_right` for copy on the left/right.
These layouts preserve the captured window's proportions without adding an
artificial display bezel. Use side layouts for narrow floating panels and
alternate composition across the deck. Other layouts keep their existing frames.

Localized product captures can be declared with
`localizations[locale][cardId].screenshot`, alongside headline and subheadline.
The locale-specific path takes precedence over `cards[].screenshot` in both
Studio and headless export. Use real captures in that language; translating only
the surrounding marketing copy does not localize the product UI.

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

## Managed Figma Production

1. Read the run snapshot, recipe, copy source, raw-capture evidence, and [figma-design-contract.md](references/figma-design-contract.md).
2. Start a leased design attempt.
3. Update deterministic source-asset nodes with raw captures.
4. Compose every required locale, scene, device class, and release theme without editing pixels inside the captured UI region.
5. Keep text editable. Enforce safe areas, contrast, line limits, locale fit, and consistent product geometry.
6. Export review artifacts at the recipe's exact size and color requirements.
7. Record the Figma file/key, page and frame identifiers, input hashes, export mapping, and visual-review notes in a registered evidence artifact; terminate the attempt.


Do not promote exports yourself. The orchestrator may request design approval only after validation succeeds; that approval is not upload approval. Record approval only through the managed approval contract with the actual human authorization reference.

For copy or framing changes, update the affected Figma frames and retain authentic captures. When product inputs change, reproduce every dependent frame using its registered input bindings. Record the new output and producer evidence in a new attempt; see the [iteration contract](../app-store-creative/references/iteration-contract.md).
