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


## Packaged macOS recorder

Requires macOS 15+, Xcode Command Line Tools, and ffprobe. A dry run never compiles,
queries windows, requests permission, or records. `--execute` is the explicit local
capture action. Screen Recording permission must already be enabled for the host;
the recorder reports missing access without triggering a system prompt.

List windows belonging to the app, then choose an explicit window ID:

```sh
python3 <runtime-root>/scripts/record_app_window.py --bundle-id com.example.app --list-windows --execute
python3 <runtime-root>/scripts/record_app_window.py --bundle-id com.example.app --window-id 42 --output takes/workflow.mov --duration 30
python3 <runtime-root>/scripts/record_app_window.py --bundle-id com.example.app --window-id 42 --output takes/workflow.mov --duration 30 --execute
```

The default is 1920×1080, 30 fps, H.264 MOV without cursor or captured audio.
Specify `--width`, `--height`, and `--fps` as needed. Variable source frame timing
is normalized during preview production. The recorder prints `RECORDING_STARTED`;
the caller then performs the app-specific journey using its approved UI tools.
It rechecks window ownership and never falls back to the desktop or another app.
It never launches or quits an application. Existing outputs and receipts are
preserved. On failure no success receipt is written; retain partial takes for
diagnosis and retry with a new filename. The adjacent `.receipt.json` records
window selection, recorder source hash, media probe, and output hash.

## Source timeline and production receipt

Example contract (paths are relative to this JSON file):

```json
{
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "duration": 15,
  "segments": [
    {"path": "takes/workflow.mov", "start": 3, "duration": 5, "has_audio": false},
    {"path": "takes/workflow.mov", "start": 18, "duration": 10, "has_audio": false}
  ]
}
```

```sh
python3 <runtime-root>/scripts/produce_app_preview.py --contract timeline.json --output preview.mp4
python3 <runtime-root>/scripts/produce_app_preview.py --contract timeline.json --output preview.mp4 --execute
```

Omitted `start` retains the existing zero-start behavior. Segment durations must
sum to the declared duration (including any end card). Execution probes sources,
rejects intervals beyond source duration and unavailable audio streams, and checks
for `drawtext` support before encoding text overlays. Image overlays remain an
alternative when that filter is unavailable. Files are never overwritten.

Execution creates `preview.receipt.json` and `preview.acceptance.png` alongside
the video; `--receipt` and `--snapshot` override their paths. The receipt binds
source and decorative-image hashes, timeline, encode command, output hash and
probe, and contact-sheet hash. Source changes during encoding prevent successful
publication. The six-frame contact sheet assists review; inspect action boundaries
and the final frame separately when the storyboard needs finer coverage.

For the v2 export flow, set `previewVideo.source` to this produced video and keep
its production receipt with the project evidence. `export --with-video` then
performs the existing store-format export. App-specific actions, demonstration
data, copy, and locale selection remain in the consuming project. Creating an ASC
version, uploading, and remote auditing remain the official ASC plugin's work.
