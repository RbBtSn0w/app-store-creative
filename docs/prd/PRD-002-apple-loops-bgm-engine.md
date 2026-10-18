# PRD-002: Apple Loops Background Music Engine

**Status:** Proposed
**Date:** 2026-10-18
**Target plugin:** app-store-creative

## Problem

App Preview videos need background music. The current runtime offers a single
synthesized ambient pad (`synthesize_ambient_bgm.py`) plus a sidechain ducking
mixer (`audio_ducking_mixer.py`). Users who want real musical character either
hand-cut audio in a DAW or source external music. The majority of this plugin's
users run macOS, where Logic Pro or GarageBand installs ship licensed Apple
Loops content that is already on disk and cleared for use in original
soundtracks. Today the runtime cannot see or use that content.

Verified on this machine (2026-10-18, re-run after GarageBand install):

- 4013 CAF files under `/Library/Audio/Apple Loops`, ~1.1 GB.
- 2676 music loops (excluding 1337 Final Cut Pro sound effects).
- 2670 music loops carry derived BPM; 1664 carry key signature; 2659 carry
  free-text descriptors (Grooving, Relaxed, Melodic, ...).
- 12+ genres: Deep House, Hip Hop, Bass House, Funk, Rock/Blues, Electro
  House, Chillwave, Indie, Vintage Breaks, World/Ethnic, Electronic/Dance,
  Modern RnB.

## Goal

Let an agent on macOS discover, understand the product context, select, and
compose background music from installed Apple Loops for App Preview videos,
with the same provenance and validation gates the plugin already applies to
visuals. The agent, not the user, performs music selection; the user only
reviews the finished candidate through the existing approval flow.

## Solution: Option A - Local loop catalog plus recommendation layer

Three narrow commands, each independently verifiable, no new runtime
dependencies. The existing Python orchestration stays in charge; audio
rendering delegates to a native Swift CLI on macOS.

### 1. `bgm scan`

Read-only walk of `/Library/Audio/Apple Loops` (plus user loop folders if
present). Parse the CAF `uuid` info-tag block (UUID
`29819273b5bf4aefb78d62d1ef90bb2c`), `info`, `desc`, and `pakt` chunks to build
a catalog JSON: path, name, pack, duration, channels, sample rate, derived
BPM, key, descriptors, genre, category. Store as a managed artifact with
provenance (scan date, tool versions, file counts, errors). No audio decoding
happens in this step, so it is fast and side-effect free.

### 2. `bgm recommend`

Input: product context (app name, category, target audience, positioning,
release-notes or marketing copy) plus the preview video candidate. Output: 3
scored candidates with receipt-style provenance: loop identity, pack, license
rationale (Apple Loops software license permits use in original soundtracks;
no standalone redistribution), and the mapping from product attributes to
music attributes (genre, tempo, descriptors, instrumentation, key). The agent
picks one default candidate and composes it; the other two remain as
one-click alternates. Human audition is not a required step in the flow.
Scoring v1 uses explicit metadata only: duration fit after loop math, BPM
range bands, descriptor match, genre affinity. No ML model.

### 3. `bgm compose`

Take the chosen loop and the preview video, and produce a final mixed video:
loop/fade chain, linked limiter, LUFS normalization to -16 LUFS, true-peak
ceiling -1 dBTP, AAC-LC 44.1 kHz stereo CBR 192 kbps, video passthrough, and
priming compensation for exact 20 s presentation. Delegates to the temporary
Swift pipeline validated during feasibility work:

- LUFS meter matched EBU Tech 3341 tests 15-23 within official tolerance
  (worst error -0.079 dB, all 9 tests pass).
- True-peak gate passed all 9 official tests within -0.4/+0.2 dB; 288
  synthetic boundary cases: 0 reference-overlimit accepted, 76 conservative
  rejections.
- Pure Swift chain matched FFmpeg loudness/peak within 0.02 dB and eliminated
  FFmpeg's 15.6 ms AAC tail and priming-delay regressions.

If the user's machine has no usable Apple Loops install, `bgm scan` returns an
empty catalog and the runtime falls back to the current agent-generated
ambient BGM path. The feature degrades, it does not block preview production.

## Non-Goals

- Bundling any loop content with the plugin.
- Redistributing Apple Loops or embedding audio samples in reports.
- Replacing the existing synthesized BGM path.
- ML-based mood scoring, auto music-generation, or multi-track arrangement
  (v1 is single-loop with loop math plus fades).
- Non-macOS hosts. On non-macOS the feature is simply unavailable and the
  fallback applies.

## MVP Slice and Success Criteria

Slice 1 (scan + recommend, no audio mutation): scan returns catalog JSON with
provenance; recommend returns 3 scored candidates with receipts derived from
product context, plus one agent-selected default. Success: on a
Logic/GarageBand machine, >=3 candidates with valid receipts in <60 s; on a
bare machine, clean empty catalog plus fallback to the synthesized BGM path.

Slice 2 (compose): Swift CLI takes chosen loop plus preview video, produces a
measured -16 LUFS / <=-1 dBTP / exact-duration output, and the candidate
validator accepts the result with the BGM receipt attached. Success: same
metrics as the temporary feasibility pipeline, plus validator gate pass.

Slice 3 (integration): `preview produce` gains an optional BGM selection
bound to product context and wired into the existing managed-attempt lease,
approval, and sealing flow. Success: a sealed delivery archive contains the
BGM provenance receipt alongside visual provenance.

Agent-selection validation (2026-10-18): for the Levelory clipboard-manager
preview, the prototype inferred "calm, organized, productivity" from the UI
journey (clipboard history -> smart filters -> uppercase transform) and
selected two candidates without human rating input:

- Driving Home Synth Pad (Ab major, 64 BPM, Relaxed/Grooving/Melodic) -
  rendered at -16.02 LUFS, -1.18 dBTP guarded true peak, 20.000 s.
- Arpeggiated Piano 01 (G minor, 85 BPM, Relaxed/Clean/Acoustic/Melodic) -
  rendered at -16.03 LUFS, -1.34 dBTP guarded true peak, 20.000 s.

Both passed the native acceptance gates in one limiter attempt. The first is
a sustained ambient bed; the second adds gentle motion matching the UI
operation cadence. They are available as the initial review artifacts in
`/private/tmp/apple-loop-feasibility/blind-test/agent-eval/`.

## Risks and Mitigations

- **Material availability varies by machine.** Not a blocker by decision: if
  Logic Pro / GarageBand content is absent, the agent uses the existing
  synthesized BGM path instead. Catalog scan is explicit and cheap; no hard
  dependency.
- **Agent judgment quality is the core bet.** The agent must infer the right
  musical tone from product context, not just match tags. Mitigation: scoring
  starts from transparent metadata rules; receipts expose the mapping from
  product attributes to music attributes; alternates are one click away; track
  acceptance rate after slices 1-2 ship.
- **License perception.** Users may worry about copyright. Mitigation: every
  candidate receipt states the source pack and license rationale; the plugin's
  existing provenance gates make this auditable rather than a claim in prose.
- **Codec timing edge cases.** FFmpeg's aac_at adds a 15.6 ms tail and the
  Swift passthrough path lost priming compensation. Mitigation: the validated
  Swift chain already handles both; keep the pipeline's native path as the
  default renderer for this feature; do not introduce a second generic MP4
  parser in Python.
- **CAF parsing fragility.** Loop tags live in a proprietary UUID-tagged block;
  format changes could break parsing. Mitigation: scanner already handles
  unknown chunks by skipping; scan errors are per-file and non-fatal.

## What Was Explicitly Set Aside

- Multi-loop arrangement and drum/bass/melody stacking (needs real user demand
  signal first).
- Windows/Linux parity (plugin user base is Mac-first; fallback path covers
  other hosts).
- ITU/EBU formal certification of the native meter (internal validation only;
  official tests passed, but this is not a certification claim).
- Bulk user-loop-folder scanning beyond `/Library/Audio/Apple Loops` (defer
  until the library path works in production).

## Next Actions

1. Run the scan/recommend slice on one more Mac without Logic/GarageBand to
   observe the empty-catalog fallback path.
2. The agent-selection prototype already rendered two context-aware
   candidates (Driving Home Synth Pad; Arpeggiated Piano 01) for the Levelory
   preview. Use these as the first review artifacts.
3. Open an ADR for the Swift CLI contract and start slice 1.

