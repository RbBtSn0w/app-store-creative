---
name: app-store-preview-producer
description: Produce App Store Preview videos from deterministic recordings of real app UI, with optional titles, transitions, audio treatment, and standards-compliant encoding. Use when a creative plan requires preview capture, editing, localization, transcoding, poster-frame review, or repair of timing, codec, dimension, or UI-authenticity defects.
---

# App Store Preview Producer

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


Build previews around recordings of the real running app. Decorative titles and transitions may be designed; product interaction pixels may not be mocked or regenerated.

For a video made in only one language, set `previewVideo.locales` to that
nonempty subset of project locales. The ASC handoff uses this exact scope;
omitting it selects the declared project locales.

## Managed Lifecycle Binding

Read the [managed specialist contract](../app-store-creative/references/specialist-lifecycle.md) and apply it to new work. Use leased attempts and registered input/output artifacts; preserve partial failures and their reasons. A producer receipt or file does not grant approval, seal a delivery, or prove remote readiness. Standalone capture/encoding executors still require this explicit registration adapter.

## Managed Window Recording

Resolve the real bundle and window ID using the consuming project's instructions. Recording requires explicit context and existing screen-recording consent; do not launch, quit, or drive an app as part of this executor. Native recording-start signals are forwarded to stderr while the final managed JSON remains on stdout.

```sh
python3 <runtime-root>/scripts/app_store_creative.py preview record --repo <repo> --run-id <run-id> --bundle-id <approved-bundle-id> --window-id <window-id> --duration 30 --logical-path sources/take.mov --owner <agent> --confirm RECORD
```

The adapter registers the take and portable recording evidence, with partial failure preservation. Real window/permission/cross-process behavior still requires product-level evidence; adapter fixtures do not prove real UI capture.

## Managed Timeline Execution

Use the managed adapter for timeline encoding after obtaining real source takes. It snapshots source files, registers the portable timeline and artifact dependencies, holds an attempt lease, and records partial failures. The selected preview carries portable encoding-receipt and acceptance-frame dependencies; unresolved absolute paths in receipt data are rejected. Receipt references use sealed-package paths under `recipe/inputs`; replay the portable timeline into a separate output directory, never over an immutable delivery. This does not record the app UI or select/approve a candidate automatically.

```sh
python3 <runtime-root>/scripts/app_store_creative.py preview produce --repo <repo> --run-id <run-id> --contract <timeline.json> --logical-path preview/app_preview.mp4 --owner <agent> --confirm EXECUTE
```

## Produce

1. Read the plan and [video-capture.md](references/video-capture.md), then start a managed preview attempt.
2. For macOS, use the packaged `record_app_window.py` executor described in [video-capture.md](references/video-capture.md); it never launches, quits, or drives the app. Record deterministic journeys with the platform-native path named by the plan: ScreenCaptureKit for macOS, `simctl` for Simulator, or another explicitly approved real-device method.
3. Keep cursor, taps, notifications, permission prompts, and sensitive data out unless the storyboard requires them.
4. Use `produce_app_preview.py` with segment `start` and `duration` to select intervals from real takes. It resolves paths relative to the contract and emits a receipt and contact sheet. Edit with `ffmpeg` or the repository-declared tool. Preserve action continuity and truthful feature behavior.
5. Encode to the plan's dimensions, orientation, frame rate, duration, codec, audio, and color constraints.
6. Export the final preview plus an acceptance snapshot containing representative frames and timing notes.
7. Record source takes, commands, hashes, media probe output, and acceptance-snapshot path in a registered evidence artifact; terminate the attempt.

```sh
python3 <runtime-root>/scripts/produce_app_preview.py --contract <contract-file> --output <preview-file>
```

Run without `--execute` to inspect the derived media command. Add `--execute` only after reviewing the contract and command.

For changed story, interaction, pacing, or locale, use the [iteration contract](../app-store-creative/references/iteration-contract.md) to isolate affected real UI segments. Register current source takes, final intervals, output hashes, and producer evidence against a new managed attempt. Do not upload or request either approval from this skill.

### Registered timeline inputs

A timeline segment, overlay, or end card may declare `artifact_id` instead of
`path`. Use the capture artifact ID returned by managed recording to preserve
its recording receipt in the preview dependency closure. The artifact must be
a verified, non-partial capture from a succeeded attempt. Declaring both fields
is an error. Managed production snapshots the referenced bytes into leased
inputs and writes a portable path-based recipe for independent archive replay.

### Managed poster frame

Use `preview poster --run-id <run-id> --preview-id <preview-artifact-id>
--timestamp <seconds> --owner <owner> --confirm EXTRACT` to extract a PNG from
an already completed preview. The shared lifecycle verifies source bytes,
records the selected time and source hash, and retains partial output on failure.
Select the returned poster artifact alongside its preview in the release
candidate. Local extraction does not grant visual approval or confirm the
remote App Store poster frame; those remain separate gates.

Set `previewVideo.posterRequired` to `true` when the release matrix requires a
poster. Candidate validation then rejects an omitted poster, as well as a poster
bound to a different preview. The default is `false` when this optional requirement is not declared;
any selected poster still requires the exact preview dependency binding.

For a failed, cancelled, or interrupted poster attempt, use `--retry-of
<attempt-id>` when retrying within the same run. Studio's poster endpoint accepts
`retry_of` with the same rules. Successful or active attempts cannot be declared
as a retry source; previous partial artifacts remain immutable evidence.
