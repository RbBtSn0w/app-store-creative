# App Store Creative

App Store Creative is an Agent-native, local-first release engine and Studio for
producing, validating, and publishing reproducible App Store screenshot and
preview releases.

It replaces heavy external design software with an instant **Localhost Canvas**
supporting connected panoramic cards, executes deterministic 1:1 headless
rendering with zero network access, and enforces Apple Store Connect constraints
before publishing.

## Key Capabilities (v2.0)

- **Localhost Studio Canvas**: Pre-bundled Vite + React studio with real Apple device bezels (iPhone 16 Pro Max, iPad, Mac) and hot reload.
- **Connected Track Support**: Continuous panoramic canvas allowing cards, decorative gradients, and tilted phones to span across screen boundaries.
- **Headless 1:1 Store Rendering**: Uses system Chrome for deterministic, zero-tolerance resolution export (1320x2868, 1290x2796, etc.) with 24-bit RGB and no alpha channel.
- **Zero-Network Release Validator**: Strictly verifies dimensions, format, file sizes, and generates immutable `.creative/release-lock.json` evidence.
- **App Preview Video Synthesizer**: Native FFmpeg automation producing compliant H.264 stereo AAC App Preview videos (15-30s).
- **ASC Publishing Handoff**: Connects safely with the official App Store Connect plugin (`asc`).

## Prerequisites

- **Python 3.10+**
- **Google Chrome** (or Chromium / Brave / Edge) for headless pixel exports.
- **FFmpeg & ffprobe** (optional, only required if generating App Preview videos).
- **ASC plugin / CLI** (optional, for remote App Store Connect publishing).

## Install from this repository

From a clone of this repository, register its repo-local marketplace and install
the plugin:

```bash
codex plugin marketplace add <repo-root>
codex plugin add app-store-creative@personal
```

Replace `<repo-root>` with the absolute path to this repository. After an
install, reinstall, or local plugin update, start a new Codex thread so plugin
discovery picks up the current manifest, skills, and versioned templates.

## Start a consuming project

Copy the files under
`plugins/app-store-creative/assets/templates/` into the consuming repository,
then adapt the project and release manifests to that product. Keep the
validator wrapper unchanged so the pinned plugin and schema versions remain
visible during review. Vendor the matching local runtime at
`.app-store-creative/runtime/0.1.0/app_store_creative.py`, or set
`APP_STORE_CREATIVE_CLI` to that exact local version. The wrapper never installs
dependencies or contacts the network.

## Agent-Native Workflow (v2.0)

In v2.0, the entire release intent is declared in a single `creative.config.json`. No Figma or external design accounts are required.

### 1. Initialize or copy the config
Copy the template to your repository:
```bash
cp plugins/app-store-creative/assets/templates/creative.config.json ./creative.config.json
```

### 2. Live Preview with Localhost Studio
Start the Studio server to interactively preview your cards, test continuous panoramic layouts, and inspect multi-locale typography:
```bash
python3 plugins/app-store-creative/scripts/app_store_creative.py dev
# Opens http://localhost:3100
```

### 3. Headless 1:1 Pixel Export
Export store-ready, 24-bit RGB PNGs across all target devices and locales in seconds:
```bash
python3 plugins/app-store-creative/scripts/app_store_creative.py export
# With App Preview video:
python3 plugins/app-store-creative/scripts/app_store_creative.py export --with-video
```

### 4. Zero-Network Release Verification
Verify that all generated assets strictly adhere to Apple App Store Connect specifications:
```bash
python3 plugins/app-store-creative/scripts/app_store_creative.py verify
# Generates immutable audit evidence: .creative/release-lock.json
```

### 5. Safe ASC Publishing
Verify the diff and hand off compliant assets to App Store Connect:
```bash
# Dry-run inspection
python3 plugins/app-store-creative/scripts/app_store_creative.py publish

# Confirm handoff
python3 plugins/app-store-creative/scripts/app_store_creative.py publish --confirm
```

---

## Stable CLI Contract (v1 Legacy Compatibility)

Every `--release` argument is a path to a JSON release manifest, not an inline
JSON value. The approval boundaries require exact, case-sensitive confirmation
words:

```bash
python3 app_store_creative.py approve \
  --repo <project-root> \
  --release <release.json> \
  --stage design \
  --approved-by <reviewer> \
  --input-manifest <review-manifest.json> \
  --confirm APPROVE

python3 app_store_creative.py promote \
  --repo <project-root> \
  --release <release.json> \
  --input-dir <approved-export-root> \
  --confirm-approved PROMOTE

python3 app_store_creative.py upload \
  --repo <project-root> \
  --release <release.json> \
  --plan <upload-plan.json> \
  --confirm-approved UPLOAD
```

For an unpromoted completed task whose source inputs changed without changing
its release-manifest fields, archive its current receipt and reopen it with:

```bash
python3 app_store_creative.py invalidate \
  --repo <project-root> \
  --run-id <run-id> \
  --task-id <task-id> \
  --actor <identity> \
  --reason <reason>
```

Invalidation preserves receipt and approval history, clears current approvals,
and makes prior upload plans stale. Create a new run for changed task fields or
for work that was already promoted.

The promotion input directory must preserve every task's relative `output`
path. For example, an output of `artifacts/en-US/mac/01-hero.png` is read from
`<approved-export-root>/artifacts/en-US/mac/01-hero.png`. This prevents
same-named files from different locales or devices from colliding.

In v0.1, the engine's `upload` command is a dry-run safety gate. It validates
the immutable plan and approvals and does not mutate App Store Connect. After
that gate passes, the publisher skill performs the actual remote mutation
through the official ASC plugin. The template therefore defaults to
`remoteWrite: false`; changing remote state always remains a separate, explicit
publisher action.

## Repository validation

The GitHub Actions workflow validates the plugin package and exercises the
same zero-network release validator wrapper shipped to consuming projects.

## License

MIT
