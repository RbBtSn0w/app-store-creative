# Validation Contract

## Structural checks

Compare actual media with the candidate matrix and immutable recipe snapshot:

- exact locales, device/display types, scenes, filenames, counts, and order;
- exact screenshot dimensions, PNG encoding, color policy, alpha policy, and hashes;
- exact preview dimensions, orientation, container, codec, frame rate, duration, audio policy, and hashes;
- no missing or unexpected media; all receipts refer to the current source revision and inputs.

Use `candidate validate` for workflow invariants and immutable validation evidence. Use platform tools such as `sips`, `file`, hashing utilities, and `ffprobe` for media facts.

## Visual checks

Inspect every screenshot, the complete preview playback, and the selected poster. Acceptance snapshots support review but cannot establish transition quality or pacing across the full video. Block product-pixel fabrication, stale UI, clipped or tiny product surfaces, black corners, double shells, alpha seams, copy overflow, poor contrast, incorrect locale, misleading claims, broken transitions, or private/debug content.

## ASC readiness

Use current official ASC capabilities to resolve IDs and build a dry-run upload plan. ASC video previews do not have an equivalent local validation command, so require local media-probe evidence plus human review of complete playback and the selected poster. Record upload, processing, playback, and poster observations independently; local decoding or a nonzero poster size cannot establish remote readiness. A dry run proves intent only; it does not prove remote state or authorize upload.

Emit blocking failures, warnings, and unproven manual boundaries separately. Never rewrite source artifacts from the validator.
