# Iteration Contract

## Purpose

Turn a creative follow-up into the smallest truthful rerun. A later export or
passing media probe never makes a stale capture trustworthy. Start from the
generated run plan and classify the change before modifying an artifact.

## Scene source map

New release tasks declare `"receipt_contract": "source-map-v1"`. The engine
then requires screenshot tasks to submit a `design` receipt and App Preview
tasks to submit a `preview` receipt. Legacy tasks without the field keep the v1
free-form receipt behavior.

Every mapping records `locale`, `appearance`, positive `geometry.width` and
`geometry.height`, `source_revision`, and an `output` whose repository-relative
path and SHA-256 match the verified task artifact. Screenshot mappings also
require `scene_id`, one or more repository-relative `source_captures` with
current SHA-256 values, and `figma_node_ids`. Preview mappings require
`segment_id`, `journey_id`, a repository-relative `source_take` with its current
SHA-256, and a valid output `interval`.

A screenshot receipt has this shape:

```json
{
  "role": "design",
  "source_map": [
    {
      "scene_id": "hero",
      "locale": "en-US",
      "appearance": "light",
      "geometry": {"width": 1320, "height": 2868},
      "source_revision": "<git-sha>",
      "source_captures": [
        {"path": "capture/en-US/hero.png", "sha256": "<sha256>"}
      ],
      "output": {
        "path": "artifacts/en-US/iphone-6.9/01-hero.png",
        "sha256": "<sha256>"
      },
      "figma_node_ids": ["123:456"]
    }
  ]
}
```

This map is the authority for impact analysis. Do not infer that an export is
current because its filename, scene ID, or output dimensions still match.

## Reopen completed work

Use `invalidate` only when source inputs changed without changing the task's
release-manifest fields. It archives the current receipt, clears current design
and upload approval pointers while retaining their immutable history, and
returns the task to `pending`:

```sh
python3 <plugin-root>/scripts/app_store_creative.py invalidate \
  --repo <repo> \
  --run-id <run-id> \
  --task-id <task-id> \
  --actor <identity> \
  --reason <reason>
```

After invalidation, claim and complete the task again. Generate a new upload
plan because plans bound to the archived receipt are stale. If task fields in
the release manifest changed, or the task was already promoted, create a new
run instead; promoted evidence is never reopened in place.

## Change routing

| Change | Re-run | Preserve |
| --- | --- | --- |
| Copy, background, framing, or other non-product design | Only affected Figma frames, then their exports and validation | Raw captures and preview takes |
| One screenshot's product state, locale, appearance, seed data, or geometry | That checkpoint's deterministic journey, then every Figma frame using its hash | Unaffected checkpoints and frames |
| App build, navigation, login, permission, or fixture change | Every dependent journey; inspect the source map rather than guessing the scope | Independent scenes with proven independence |
| Preview story, interaction, pacing, or locale | Only affected real-UI segments, then encode, probe, acceptance snapshot, and validation | Unaffected source takes |
| Device target, App Store requirement, or release-manifest policy | All artifacts selected by that requirement, then full release validation | Nothing merely because the visual layout is unchanged |

For a broken deterministic journey, reproduce the individual checkpoint first.
Capture the failing step, expected ready state, actual visible state, and the
selector or accessibility seam that changed. Repair the narrowest journey or
test seam; never paper over a journey failure with a manual screenshot.

## Completion evidence

When an iteration is complete, record the changed inputs, retained input
hashes, commands, replacement outputs, and the validation result in the
role-specific source map. Invalidated outputs must not be offered for design
approval or promotion until their dependent work has completed.
