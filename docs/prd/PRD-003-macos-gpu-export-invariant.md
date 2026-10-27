# PRD-003: macOS GPU-Accelerated Export Invariant

**Status:** Implemented (Sprint 001)
**Date:** 2026-10-19
**Owner:** rbbtsn0w
**Depends on:** ADR-001 (export proportional scaling), ADR-002 (artifact lifecycle)
**Priority:** P0

## Problem Statement

`export_engine.py` unconditionally appends `--disable-gpu` to every headless
Chrome invocation; the native launcher (`chrome_renderer.py`) filters the
flag only when the Chrome binary lives inside a `.app` bundle. Chrome
installed via Homebrew (a bare executable, no `.app` parent) therefore runs
with GPU compositing disabled on macOS, violating the project invariant
documented in `SKILL.md` that macOS exports must not disable the GPU. The
pixel-level quality impact is an assumption to be validated by the
acceptance tests below; the verified risks are the SwiftShader software-
rasterization behavior recorded in `SKILL.md`.

Users affected: any macOS user with a non-bundle Chrome installation
(Homebrew, manual binary installs). Frequency: every export. Cost of not
solving: silent quality degradation on a flagship feature, and a documented
invariant that the code contradicts — a credibility gap for a
provenance-first product.

## Goals

1. Every Chrome invocation on macOS runs with GPU compositing enabled,
   regardless of how Chrome was installed.
2. Non-macOS platforms retain the `--disable-gpu` flag (headless Linux CI
   relies on it for determinism).
3. The macOS GPU invariant is enforced by test, not by convention.

## Non-Goals

- Not redesigning the Chrome launch pipeline or its flag set.
- Not adding GPU fallback/detection logic (software rendering fallbacks) —
  out of scope; macOS GPU availability is assumed.
- Not changing the `--force-device-scale-factor` scaling contract defined in
  ADR-001.

## User Stories

- As a macOS engineer using a Homebrew-installed Chrome, I want exports to
  render with GPU compositing so that my 3D card layers rasterize at full
  Retina quality.
- As a CI maintainer, I want Linux headless exports to keep GPU disabled so
  that screenshots remain deterministic across runners.

## Requirements

### Must-Have (P0)

- **R1**: On `sys.platform == "darwin"`, the final executed Chrome argv
  contains no `--disable-gpu`, for both bundle and non-bundle Chrome
  installs (one platform-level policy; the `.app`-bundle filter branch is
  removed).
  - *Acceptance*: Unit tests assert the final argv for a bundle path and a
    bare path (e.g. `/Applications/Google Chrome.app/...` and
    `/opt/homebrew/bin/chrome`) contain no `--disable-gpu` on macOS.
- **R2**: On non-macOS platforms, `--disable-gpu` remains in the final
  executed argv.
  - *Acceptance*: Unit test asserts the flag list for a Linux path (e.g.
    `/usr/bin/chromium`) includes `--disable-gpu`.

### Nice-to-Have (P1)

- **R3**: Diagnostic log line when the flag list is built, stating platform
  and whether GPU is enabled.
  - *Acceptance*: Manual smoke run on macOS shows the diagnostic in stderr.

### Future Considerations (P2)

- Refactor flag-list construction into a pure function separate from the
  export call, so future platform-specific flag policies are testable without
  invoking Chrome.

## Success Metrics

- **Leading**: The platform-invariant unit tests pass for bundle and
  non-bundle Chrome on macOS, and for Linux with the flag retained.
- **Lagging**: macOS smoke exports (per release) complete within the
  documented render-time budget with GPU compositing enabled; a pixel
  comparison against a GPU-enabled baseline shows no systematic
  degradation.

## Open Questions

- *(engineering, resolved)* All CI jobs run on `ubuntu-latest`
  (`.github/workflows/ci.yml`); no macOS runner exists, so Linux keeps
  `--disable-gpu` for determinism and nothing depends on the macOS change.
  *Update:* CI test and validation jobs now run on `macos-15` because the
  plugin is macOS-only; the Linux `--disable-gpu` branch remains covered by
  the patched-platform unit tests.
- *(engineering, resolved)* The `.app`-bundle filter branch is removed; the
  platform check becomes the single GPU policy (folded into R1).

## Timeline Considerations

- Small, low-risk change (~a few lines + tests). Can land independently of
  other PRDs in this batch.
- No hard deadline, but should precede any macOS CI runner introduction,
  since that runner will exercise the non-`.app` Chrome path directly.
