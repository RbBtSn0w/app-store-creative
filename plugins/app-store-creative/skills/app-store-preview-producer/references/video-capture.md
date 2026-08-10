# Video Capture and Preview Contract

## Record real UI

Use ScreenCaptureKit for macOS, `xcrun simctl io <device> recordVideo` for Simulator, or a plan-approved real-device capture path. Record the actual app journey with deterministic data and geometry. Never substitute an animation or generated replica for product interaction.

Capture clean handles around each action. Avoid sensitive data, unrelated system chrome, notifications, permission prompts, cursor/tap indicators, and nondeterministic loading unless explicitly part of the storyboard.

## Edit and encode

Treat the repository manifest as the authority for orientation, dimensions, duration, frame rate, codec, container, audio, and localization variants. Use `ffmpeg` or the declared editor reproducibly. Decorative titles and transitions must not imply behavior the app does not provide.

Inspect the final with:

```sh
ffprobe -v error -show_streams -show_format -of json <preview-file>
```

## Acceptance snapshot

Create a contact sheet or equivalent snapshot with the first frame, each major interaction, every title card, transition boundaries, and the final frame. Include timestamps and a short continuity note. This is required because media metadata alone cannot prove visual authenticity or editorial quality.

Record source-take hashes, edit/encode commands, final hash, `ffprobe` output, duration, and acceptance-snapshot path in the receipt.
