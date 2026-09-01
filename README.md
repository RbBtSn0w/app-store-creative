# App Store Creative

App Store Creative is a local-first Codex plugin for planning, producing,
validating, and publishing reproducible App Store screenshot and preview
releases.

The plugin keeps creative intent in versioned project and release manifests.
Its validation path is deterministic and requires no network access, making the
same release gate suitable for local development and CI.

## Prerequisites

Install the official Figma plugin for design-source work and the ASC plugin for
App Store Connect lookup and publishing handoff. App Store Creative does not
declare either integration in its manifest: every external read or write stays
explicit and attributable to the corresponding plugin.

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

## Stable CLI contract

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
