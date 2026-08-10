# Capture Contract

## Determinism

- Pin app build, seed data, locale, time-sensitive values, appearance, scale, device/window size, and capture naming.
- Disable animations when they make checkpoint timing unstable; otherwise wait on a semantic ready condition.
- Prefer accessibility identifiers and visible state assertions over sleeps.
- Avoid pre-existing user state, network-dependent content, notifications, permission sheets, and private data.

## Authenticity

Every pixel inside the product viewport must originate from the running app. Cropping a real capture is allowed when the manifest calls for it. Redrawing, retouching controls, replacing content, or generating a plausible UI is not allowed.

## Checkpoint evidence

For each planned scene, record the journey/test identifier, attachment name, output file, locale, appearance, dimensions, scale, and SHA-256. Note any manual prerequisite. Preserve raw files independently from composed exports.

Block the handoff for blank content, wrong account/data, debug UI, focus artifacts, cursor leakage, clipped windows, black or opaque corners, unintended scrollbars, or dimensions that disagree with the plan.
