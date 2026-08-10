# Validation Contract

## Structural checks

Compare actual media with the plan and release manifest:

- exact locales, device/display types, scenes, filenames, counts, and order;
- exact screenshot dimensions, PNG encoding, color policy, alpha policy, and hashes;
- exact preview dimensions, orientation, container, codec, frame rate, duration, audio policy, and hashes;
- no missing or unexpected media; all receipts refer to the current source revision and inputs.

Use the engine `verify` command for workflow invariants. Use platform tools such as `sips`, `file`, hashing utilities, and `ffprobe` for media facts.

## Visual checks

Inspect every screenshot and the preview acceptance snapshot. Block product-pixel fabrication, stale UI, clipped or tiny product surfaces, black corners, double shells, alpha seams, copy overflow, poor contrast, incorrect locale, misleading claims, broken transitions, or private/debug content.

## ASC readiness

Use current official ASC capabilities to resolve IDs and build a dry-run upload plan. ASC video previews do not have an equivalent local validation command, so require both `ffprobe` evidence and human inspection of the acceptance snapshot. A dry run proves intent only; it does not prove remote state or authorize upload.

Emit blocking failures, warnings, and unproven manual boundaries separately. Never rewrite source artifacts from the validator.
