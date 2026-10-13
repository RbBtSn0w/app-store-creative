# Iteration Contract

## Purpose

Turn a creative follow-up into the smallest truthful rerun. A later export or
passing media probe never makes a stale capture trustworthy. Start from the
managed run snapshot and classify the change before modifying an artifact.

## Dependency authority

Managed artifact IDs and their immutable input bindings are the authority for affected work. Producer evidence must identify locale, appearance, geometry, source revision, capture checkpoints or preview intervals, output hashes, and relevant Figma nodes. Inspect the recorded inputs rather than guessing from a scene name or unchanged dimensions.

Create a new run when the recipe or source snapshot changes. Retry failed production in a new attempt with `retry_of` pointing to the original attempt. Never reopen or overwrite sealed deliveries, old attempts, or approval records. Revalidate a new candidate and obtain fresh approvals for changed evidence. Comprehensive automatic dependency invalidation remains an implementation requirement; agents must inspect dependency closure explicitly until that capability is verified.

## Change routing

| Change | Re-run | Preserve |
| --- | --- | --- |
| Copy, background, framing, or other non-product design | Only affected Figma frames, then their exports and validation | Raw captures and preview takes |
| One screenshot's product state, locale, appearance, seed data, or geometry | That checkpoint's deterministic journey, then every Figma frame using its hash | Unaffected checkpoints and frames |
| App build, navigation, login, permission, or fixture change | Every dependent journey; inspect the source map rather than guessing the scope | Independent scenes with proven independence |
| Preview story, interaction, pacing, or locale | Only affected real-UI segments, then encode, probe, full preview playback and selected-poster review, and validation | Unaffected source takes |
| Device target, App Store requirement, or recipe policy | All artifacts selected by that requirement, then full candidate validation | Nothing merely because the visual layout is unchanged |

For a broken deterministic journey, reproduce the individual checkpoint first.
Capture the failing step, expected ready state, actual visible state, and the
selector or accessibility seam that changed. Repair the narrowest journey or
test seam; never paper over a journey failure with a manual screenshot.

## Completion evidence

When an iteration is complete, record the changed inputs, retained input
hashes, commands, replacement outputs, and the validation result in the
registered producer evidence. Stale outputs must not be offered for design
approval or promotion until their dependent work has completed.
