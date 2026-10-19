# ADR-003: Apple Loops BGM Engine - Swift CLI Contract and Slice Boundaries

**Status:** Accepted (Slices 1–4 implemented; slice 5 pending manual validation)
**Date:** 2026-10-18
**Deciders:** rbbtsn0w, Codex Agent
**Depends on:** PRD-002

## Context

PRD-002 proposes an Apple Loops background-music engine for App Preview
videos. Technical feasibility has been verified end to end in temporary
experiments: a pure Swift pipeline reads CAF, applies loop math and fades,
runs a linked limiter, normalizes to -16 LUFS, gates true peak at -1 dBTP,
encodes AAC-LC 44.1 kHz stereo CBR 192 kbps, muxes with the video track via
AVAssetExportSession passthrough, restores AAC priming compensation, and
verifies the final presented audio. The pipeline passed 9/9 EBU Tech 3341
loudness tests and 288 synthetic true-peak boundary cases. Agent-driven music
selection was demonstrated on the Levelory preview with two context-aware
candidates rendered in one limiter attempt each.

This ADR fixes the implementation contract before any production code is
written, so that the three PRD slices (scan, recommend, compose) have
unambiguous boundaries, tool ownership, and acceptance gates.

## Decision

### Architecture: Python orchestrates, Swift renders

The existing runtime is Python-based (lifecycle kernel, records, CLI). Audio
decode, DSP, and AVFoundation muxing require macOS system frameworks that are
most reliably accessed from Swift. The split:

| Layer | Language | Responsibility |
|-------|----------|----------------|
| Lifecycle, catalog, receipts, scoring | Python | Read CAF headers, build catalog, score candidates, manage records, invoke Swift binary |
| Audio render + mux | Swift CLI | Decode CAF via AVAudioFile, loop/fade, limiter, LUFS, true-peak gate, AAC encode, video mux, priming restore, final verify |

This matches the plugin's existing pattern (Python orchestration delegating
media production to specialized tools) and keeps the Swift surface minimal:
one subcommand, JSON in and out, no filesystem or record management inside
the binary.

### Swift CLI contract: `swift-bgm compose`

A single-purpose binary with one public subcommand in v1:

```
swift-bgm compose \
  --loop <caf-path> \
  --video <mp4-path> \
  --output <mp4-path> \
  [--fade-in 0.35] \
  [--fade-out-duration 1.5] \
  [--target-lufs -16.0] \
  [--true-peak-ceiling -1.0]
```

Note: the implemented flags are `--fade-in`, `--fade-out-start`,
`--fade-out-duration`, `--target-lufs`, and `--true-peak-ceiling` (matching the
parser in `swift_bgm_compose.swift`). When `--fade-out-start` is omitted, the
binary derives it from the video duration (`duration - fade-out-duration`) so
the fade-out window adapts to each preview.

Behavior:

1. Read the CAF loop with `AVAudioFile` (float32, non-interleaved).
2. Tile the loop to the video's audio duration (read from the video asset),
   apply linear fade-in from 0 and fade-out from the configured start point.
3. Resample to 4x for true-peak measurement, run the linked limiter, resample
   back, encode AAC-LC CBR 192 kbps via `AVAssetWriter`.
4. Mux the encoded audio with the source video track via
   `AVAssetExportSession` passthrough (video bitstream unchanged).
5. Restore AAC priming compensation by patching the audio `elst` media start
   in the output MP4, using the source M4A's packet table.
6. Decode the final output, measure LUFS and guarded true peak, and verify:
   |LUFS - target| <= 0.1, guarded peak <= ceiling, presentation duration
   matches the video.
7. On success, print a JSON receipt to stdout and exit 0. On failure, print a
   structured error to stderr and exit nonzero; the output file is not
   promoted.

Receipt schema (v1):

```json
{
  "attempts": [{"attempt": 0, "drive_db": ..., "limiter_ceiling_db": ..., "max_gain_reduction_db": ..., "pcm_lufs": ..., "aac_lufs": ..., "aac_guarded_peak_dbtp": ...}],
  "final_native_lufs": ...,
  "final_native_guarded_peak_dbtp": ...,
  "final_native_frames": ...,
  "presentation_frames": ...,
  "restored_priming_frames": ...,
  "duration_seconds": ...,
  "output": "<path>",
  "elapsed_seconds": ...
}
```

**Binary distribution:** compile on first use via `swiftc` (Xcode Command
Line Tools), cache the binary in the runtime work directory, and report a
clear error if `swiftc` is unavailable. Do not ship a pre-compiled binary in
the plugin payload. The target audience runs macOS with developer tools
installed; shipping a universal binary adds payload weight and signing
complexity for no gain.

**Known limitation - priming restore:** the `elst` patcher is a narrow
experiment adapter validated on 44.1 kHz stereo AAC-LC with exact
882000-sample presentation and single-track MP4. It does not handle
multi-track audio, non-44.1 kHz rates, or unusual MP4 structures. The compose
contract explicitly restricts v1 input to single-video-track, single-audio-
track MP4 previews. Generalizing the MP4 parser is out of scope; revisit only
if real previews hit the boundary.

### Python side: scan and recommend

**`bgm scan`** (pure Python, no audio decode, no Swift dependency):

- Walk `/Library/Audio/Apple Loops` (fixed path; user-loop directories are a
  future extension).
- Parse CAF headers: `caff` magic, `desc` (sample rate, channels), `pakt`
  (frame count), `info` and `uuid` info-tag block (UUID
  `29819273b5bf4aefb78d62d1ef90bb2c`) for metadata key-value pairs.
- Derive BPM from `beat count` and duration.
- Output: catalog JSON with provenance (scan date, file counts, errors,
  library root). Register as a managed artifact per the lifecycle kernel.
- Acceptance: zero errors on a healthy library; clean empty catalog plus
  fallback message on a bare machine; per-file parse errors are non-fatal and
  recorded.

**`bgm recommend`** (pure Python, reads catalog + product context):

- Input: catalog JSON + product context (app name, category, target audience,
  positioning, optional marketing copy). Context comes from
  `creative.config.json` fields or explicit CLI arguments; no separate
  context file in v1.
- Scoring v1: transparent metadata rules (descriptor match, BPM range bands,
  genre affinity, duration fit after loop math, instrumentation preference by
  category). No ML model.
- Output: 3 scored candidates with receipts (loop identity, pack, license
  rationale, product-attribute-to-music-attribute mapping) plus 1 agent-
  selected default. Receipts are structured JSON, registered as artifacts.
- The agent (LLM) performs the final selection from the 3 candidates using
  product context; the scoring provides a ranked shortlist, not a mandate.
- Acceptance: >=3 candidates with valid receipts in <60 s on a healthy
  library; receipts pass schema validation; the default candidate's mapping
  is traceable from receipt fields alone.

**`bgm compose`** (Python orchestrator invoking the Swift binary):

- Input: chosen loop path + preview video path + optional fade parameters.
- Invokes `swift-bgm compose`, captures the JSON receipt, registers both the
  output MP4 and the receipt as artifacts with dependency links.
- If the Swift binary is not yet compiled, compiles it first and caches.
- Acceptance: output MP4 passes the same gates the temporary pipeline
  verified (LUFS, true peak, duration, priming); validator accepts the
  candidate with the BGM receipt attached.

### Slice boundaries and ownership

| Slice | Scope | New code | Swift binary needed | Depends on |
|-------|-------|----------|--------------------|------------|
| 1. scan | CAF header parser + catalog output + artifact registration | Python | No | Lifecycle kernel (existing) |
| 2. recommend | Scoring + receipts + agent-selection hook | Python | No | Slice 1 |
| 3. compose | Swift CLI binary + Python invocation wrapper + artifact registration | Swift + Python | Yes (compiled on demand) | Slice 2 for default candidate; works standalone with explicit paths |

Each slice is independently testable and shippable. Slice 3 can be exercised
without slices 1-2 by passing explicit paths (useful for testing and for the
temporary-experiment workflow).

## Options Considered

### Option A: Python orchestrates + Swift renders (Selected)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium - two languages, but each does what it does best |
| Correctness | High - Swift owns AVFoundation/CoreAudio; Python owns records |
| Maintainability | Good - clear boundary, minimal Swift surface (one subcommand) |
| Risk | Priming patcher is file-shape-specific; documented and bounded |

**Pros:** matches existing architecture; AVFoundation reliability proven in
experiments; Python lifecycle kernel untouched; Swift CLI is stateless and
testable; no FFmpeg dependency for this feature.

**Cons:** two languages to maintain; `swiftc` required at runtime; priming
restore is narrow.

### Option B: Pure Python + FFmpeg (existing tools only)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low - one language, existing tool |
| Correctness | Medium - FFmpeg aac_at adds 15.6 ms tail; priming handling requires manual MP4 patching in Python; loudness/peak measurement differs from native |
| Maintainability | High - single language |
| Risk | Codec timing edge cases; no system-framework decode for CAF |

**Pros:** no new binary; reuses existing FFmpeg dependency.

**Cons:** CAF decode via FFmpeg is less reliable than AVAudioFile; AAC timing
issues already diagnosed; priming restore in Python would need a general MP4
parser or remain equally narrow; LUFS/true-peak measurement would rely on
FFmpeg filters rather than the validated Swift meter.

**Rejected because:** the temporary experiments demonstrated that the pure
Swift chain produces measurably better output (exact duration, no tail, native
meter validation) at the cost of one compiled binary. The complexity trade is
worth it for a media-quality feature.

### Option C: Pure Swift (Swift owns everything including lifecycle)

| Dimension | Assessment |
|-----------|------------|
| Complexity | High - rewrite lifecycle kernel, records, CLI in Swift |
| Correctness | High for audio; but lifecycle is already Python |
| Maintainability | Poor - duplicating existing infrastructure |

**Rejected because:** the lifecycle kernel, records, artifact management, and
CLI are established Python infrastructure. Rewriting them in Swift to avoid a
two-language boundary is not justified when the Swift surface can be one
stateless subcommand.

## Consequences

**Easier:**
- Clear ownership: Python for orchestration/records, Swift for media DSP.
- Each slice lands independently; slice 3 does not block on slices 1-2.
- The Swift CLI is stateless: JSON in, JSON out, no filesystem management.
  Easy to test, easy to reason about, easy to replace later.
- No FFmpeg subprocess for BGM production; the existing FFmpeg dependency
  remains for other preview work.

**Harder:**
- Two build targets to maintain (Python scripts + one Swift file compiled on
  demand). The Swift file is expected to stay under ~500 lines.
- `swiftc` is a runtime dependency for slice 3. Acceptable for the target
  audience (macOS developers); the error message must be actionable.
- The priming-restore adapter is bounded to a specific MP4 shape. If a real
  preview falls outside it, compose fails with a clear error rather than
  producing a silently broken output. Generalizing is deferred until needed.

**Enables:**
- A validated native audio meter (-16 LUFS / -1 dBTP) that can be reused for
  other audio paths in the plugin (voiceover normalization, ducking master).
- Agent-driven music selection as a product differentiator.
- Future extension: user loop folders, multi-loop arrangement, ML scoring -
  all slot into the same Python-side scoring and Swift-side rendering
  boundary.

## Action Items

1. [x] Slice 1: implement `bgm scan` (Python) + tests + artifact registration.
2. [x] Slice 2: implement `bgm recommend` (Python) + scoring + receipts + tests.
3. [x] Slice 3: implement `swift-bgm compose` (Swift source in runtime) +
       compile-on-demand wrapper + Python invocation + artifact registration.
4. [x] Integration: standalone `bgm compose --managed` registers composed
       media, loop/video inputs and the Swift receipt as producer-evidence in
       the artifact lifecycle (PRD-004).
5. [ ] Validate slice 3 on the Levelory preview and compare against the
       temporary-experiment outputs (byte-identical not required; metrics
       within tolerance).

