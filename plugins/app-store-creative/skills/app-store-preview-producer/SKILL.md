---
name: app-store-preview-producer
description: Produce App Store Preview videos from deterministic recordings of real app UI, with optional titles, transitions, audio treatment, and standards-compliant encoding. Use when a creative plan requires preview capture, editing, localization, transcoding, poster-frame review, or repair of timing, codec, dimension, or UI-authenticity defects.
---

# App Store Preview Producer

Build previews around recordings of the real running app. Decorative titles and transitions may be designed; product interaction pixels may not be mocked or regenerated.

## Produce

1. Read the plan and [video-capture.md](references/video-capture.md), then claim the preview task.
2. Record deterministic journeys with the platform-native path named by the plan: ScreenCaptureKit for macOS, `simctl` for Simulator, or another explicitly approved real-device method.
3. Keep cursor, taps, notifications, permission prompts, and sensitive data out unless the storyboard requires them.
4. Edit with `ffmpeg` or the repository-declared tool. Preserve action continuity and truthful feature behavior.
5. Encode to the plan's dimensions, orientation, frame rate, duration, codec, audio, and color constraints.
6. Export the final preview plus an acceptance snapshot containing representative frames and timing notes.
7. Record source takes, commands, hashes, media probe output, and acceptance-snapshot path in the receipt; complete the task.

```sh
python3 <plugin-root>/scripts/produce_app_preview.py --contract <contract-file> --output <preview-file>
python3 <plugin-root>/scripts/app_store_creative.py claim --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id>
python3 <plugin-root>/scripts/app_store_creative.py complete --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id> --receipt <receipt-file>
```

Run without `--execute` to inspect the derived media command. Add `--execute` only after reviewing the contract and command.

For changed preview story, interaction, pacing, or locale, use the orchestrator's [iteration contract](../app-store-creative/references/iteration-contract.md) to isolate affected real-UI segments before encoding again. For `source-map-v1`, complete with a `preview` receipt that binds each final interval to its current source-take and output hashes. Do not upload or request either approval from this skill.
