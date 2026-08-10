# Figma Design Contract

## External dependency

Use the official Figma plugin. Load `figma-use` before invoking `use_figma`; load the appropriate official generation/library skill for creation work. Follow its current tool contract instead of embedding connector calls here.

## File structure

Keep stable pages or sections for source assets, reusable components/tokens, release frames, and review evidence. Use deterministic frame and source-node names derived from locale, scene, theme, and device class. Update existing nodes when possible so review history remains meaningful.

## Product pixels

Place raw captures as unmodified image fills within masks. Allow only plan-declared cropping and scaling. Do not paint over, redraw, warp, recolor, sharpen, or generate product UI. Keep decorative shells, backgrounds, titles, and badges outside the product-pixel layer.

## Localization and layout

- Use repository copy verbatim unless the owner approves a copy change.
- Keep text editable and use fonts licensed for production export.
- Enforce the manifest safe area, hierarchy, contrast, line limits, and product scale.
- Inspect every locale; do not approve from the source locale alone.
- Maintain scene order and stable export names from the manifest.

## Handoff

Export exact-size review files and record file/key, page IDs, frame/node IDs, source hashes, export paths, and exceptions. A reviewer must inspect clipping, seams, black corners, typography, product authenticity, and locale completeness before design approval.
