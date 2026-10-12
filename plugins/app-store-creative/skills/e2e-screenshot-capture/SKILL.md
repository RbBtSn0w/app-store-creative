---
name: e2e-screenshot-capture
description: Capture deterministic, named screenshots of real product UI through an application's existing E2E or UI-test journeys. Use when an App Store creative plan needs raw screenshot inputs, capture coverage must change, or stale, mocked, nondeterministic, incorrectly sized, or visually corrupted source pixels must be diagnosed and recaptured.
---

# E2E Screenshot Capture

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


Preserve the established contract: screenshot pixels must come from the running product UI, not a recreation, mock, Figma redraw, or generated image.

## Managed Lifecycle Binding

Read the [managed specialist contract](../app-store-creative/references/specialist-lifecycle.md) and apply it to new work. Use leased attempts and registered input/output artifacts; preserve partial failures and their reasons. A producer receipt or file does not grant approval, seal a delivery, or prove remote readiness. Standalone capture/encoding executors still require this explicit registration adapter.

## Capture

1. Read the run plan and the repository's own test instructions.
2. Start a managed capture attempt before work.
3. Use existing UI-test/E2E journeys when available. Add the narrowest deterministic journey or accessibility seam only when required.
4. Seed stable data, locale, appearance, window/device geometry, and animation state.
5. Capture named checkpoints after the UI reaches a verifiable ready state.
6. Inspect every output for stale content, permission prompts, cursors, focus rings, clipping, blank surfaces, and unexpected chrome.
7. Write a receipt listing command, environment, source revision, checkpoint-to-file mapping, dimensions, and hashes; then register the receipt and terminate the attempt.


Do not claim success from a focused test alone when the product boundary requires a real window, device, permission, or cross-process interaction. Preserve raw captures; downstream design may frame or annotate them but must not alter their UI content.

Read [capture-contract.md](references/capture-contract.md) when defining checkpoints or receipt evidence. Read the orchestrator's [iteration contract](../app-store-creative/references/iteration-contract.md): reproduce affected checkpoints first and recapture outputs according to registered input dependencies. Use the orchestrator's [agent handoff contract](../app-store-creative/references/agent-handoff.md) for leases and completion.
