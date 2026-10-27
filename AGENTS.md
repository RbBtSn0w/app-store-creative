# App Store Creative Engine Development Guidelines

This document outlines the architectural rules, CI invariants, testing standards, and development workflows for the `app-store-creative` plugin and its integrated Studio.

---

## 1. Testing & Continuous Integration (CI) Invariants

### Python Testing Standards
- **Standard Library Only**: All Python test suites in `tests/` MUST strictly inherit from `unittest.TestCase` (`import unittest`).
- **No Third-Party Test Frameworks**: Do NOT introduce `import pytest` or pytest-specific fixtures (such as `tmp_path`). The CI runner executes in a lean Python environment without `pytest` installed.
- **Filesystem Isolation**: Use `tempfile.TemporaryDirectory()` for filesystem isolation in tests instead of pytest fixtures:
  ```python
  with tempfile.TemporaryDirectory() as tmp_dir:
      tmp_path = Path(tmp_dir)
      ...
  ```
- **Exception Assertions**: Use `self.assertRaises(...)` or `self.assertRaisesRegex(...)` for exception assertions.
- **macOS-Only CI**: The plugin only runs on macOS, so CI test and validation jobs run on `macos-15` runners (ffmpeg via Homebrew). Do not move them back to Linux or rely on Linux-only behavior.
- **Authoritative CI Test Command**: In CI, unit tests are sharded across parallel matrix runners via:
  ```bash
  python3 .github/run_sharded_tests.py --shard ${{ matrix.shard }} --total 4
  ```
  Local test verification can execute the full suite using:
  ```bash
  python3 -m unittest discover -s tests -p 'test_*.py'
  ```
  or run an individual shard via `python3 .github/run_sharded_tests.py --shard 1 --total 4`.

---

## 2. Frontend (Studio) Validation Triad

When modifying Studio components (`plugins/app-store-creative/studio/`):
- **Mandatory Triad Gate**: Before staging or committing frontend changes, run all three validation steps:
  ```bash
  cd plugins/app-store-creative/studio
  npm test          # 1. Vitest unit tests
  npx tsc --noEmit  # 2. Strict TypeScript type check (catches TS6133 unused locals)
  npm run build     # 3. Production build and sync to runtime/studio/dist/
  ```
- **No Unused Locals**: `tsconfig.json` enforces `"noUnusedLocals": true`. Vitest alone will not catch unused destructuring variables; `npx tsc --noEmit` is required to guarantee clean CI builds.
- **Synchronized Dist Bundle**: The built assets in `plugins/app-store-creative/skills/app-store-creative/runtime/studio/dist/` are tracked in version control and must remain in sync with the source code.

---

## 3. CLI Architecture & Argparse Conventions

### Shared Subparser Flags
- When subparsers (`ppo list`, `ppo plan`, `ppo handoff`) share arguments defined on a parent parser (e.g. `--repo`), the subparser argument MUST use `default=argparse.SUPPRESS`:
  ```python
  ppo_list.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
  ```
- **Rationale**: Python's `argparse` applies subparser defaults after parsing parent arguments. Without `argparse.SUPPRESS`, subparser defaults silently overwrite values passed before the subcommand (e.g. `ppo --repo /custom list`).

### Defensive Path Resolution
- Resolve paths against the repository root using `project_path()` to ensure commands behave identically regardless of invocation working directory.

---

## 4. Schema Validation & Defensive Type Checking

### Python Boolean Inheritance Pitfall
- In Python, `bool` is a subclass of `int` (`isinstance(True, int) == True`). When enforcing strict integer inputs (e.g., `trafficProportion`), always explicitly reject booleans:
  ```python
  if isinstance(val, bool) or not isinstance(val, int) or not (1 <= val <= 100):
      raise ValueError(...)
  ```

### Canonical String Normalization
- Enums and platform identifiers (`MAC_OS`, `IOS`, `TV_OS`, `VISION_OS`) must be normalized to canonical uppercase immediately upon ingestion to prevent delivery path resolution mismatches.

---

## 5. 3D Spatial Canvas & Export Scaling Invariants

### Mathematical Dimension Exactness (`TARGET_BASE_SCALING`)
- All target devices defined in `TARGET_DIMENSIONS` must have exact integer scale factors registered in `TARGET_BASE_SCALING` (Studio) and `TARGET_SPECS` (Python export engine):
  - Phones: $3.0\times$
  - Tablets and Mac: $4.0\times$
  - Feature Graphics / Watch: $2.0\times$
- Scale factors and base dimensions must satisfy:
  $$\text{round}(\text{base\_w} \times \text{scale}) == \text{phys\_w} \quad \text{and} \quad \text{round}(\text{base\_h} \times \text{scale}) == \text{phys\_h}$$
- Never use heuristic fractional base dimensions that cause 1-pixel rounding drift (e.g., $2048 \times 2731$ instead of $2048 \times 2732$).

### Headless Chromium High-DPI Rendering
- Chromium headless exports must launch with `--force-device-scale-factor` matching the target device scale factor to ensure 3D CSS hardware compositor layers (`cc::PictureLayerImpl`) rasterize at native Retina resolution without downsampling artifacts.
