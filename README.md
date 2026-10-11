# App Store Creative

App Store Creative prepares App Store screenshots, preview videos, posters, and their provenance through one local artifact lifecycle. CLI, Studio, and agents share immutable records, leased production attempts, content-addressed media, candidate validation, human approvals, and sealed delivery archives. The official ASC plugin owns App Store Connect authentication and remote execution.

The unified redesign is under development on `feat/unified-artifact-lifecycle-v2`; it is not a completed release. See [implementation status](docs/adr/ADR-002-implementation-status.md) and the [delivery closure audit](docs/adr/ADR-002-delivery-closure.md) for remaining gates. The new contract has no historical compatibility requirement. Old task commands, release manifests, and standalone validation/publication writes are removed; existing consumer files are not automatically migrated or deleted.

## Runtime and prerequisites

The complete installed payload lives at `<plugin-root>/skills/app-store-creative/runtime`, including scripts, schemas, templates, and the bundled Studio. Specialist installs require the main skill so the runtime remains available. Source-tree links are development conveniences; consumers use the installed payload.

Use Python 3.11 or newer, a supported Chrome-family browser for screenshot rendering, and FFmpeg/ffprobe for video production and validation. The shell launcher prefers Homebrew Python on macOS; `APP_STORE_CREATIVE_PYTHON` selects an explicit interpreter. Figma is an optional design executor. ASC is required for remote operations.

## Consuming project

Copy `runtime/assets/templates/creative.config.json` into the product repository and set its stable project identity, localized cards, real UI captures, target devices, and storage roots. The effective storage order is defaults, shared project configuration, then the adjacent protected `creative.config.local.json`. Local configuration selects storage roots and named host-local filesystem media backends; it cannot override shared archive or artifact policies and must be untracked and ignored by actual Git policy.

```sh
CREATIVE_RUNTIME=/absolute/path/to/plugin/skills/app-store-creative/runtime
CREATIVE_REPO=/absolute/path/to/product
creative() {
  "$CREATIVE_RUNTIME/scripts/app-store-creative" "$@"
}
creative --help
creative storage inspect --repo "$CREATIVE_REPO"
creative storage git-policy --repo "$CREATIVE_REPO" --media-mode lfs
creative studio --repo "$CREATIVE_REPO"
```

Review Git rule suggestions before applying them. Four configurable roots separate working records, content objects, sealed releases, and publication evidence. Moving existing storage requires the explicit relocation plan/prepare/switch/recovery workflow; editing paths alone does not relocate records.

## Managed production and release

Import authentic product captures through `input import`. Use managed screenshot export, `preview record`, `preview produce`, and `preview poster` for production. Each attempt owns its lease and isolated working files; failed or interrupted output remains evidence, and retries create new attempts.

```sh
creative export --repo "$CREATIVE_REPO"
creative candidate validate --repo "$CREATIVE_REPO" --id "$CREATIVE_CANDIDATE_ID"
```

Use actual IDs returned by commands. Select the complete ordered candidate and validate its source dependencies and media matrix. Review visuals separately, record the human design authorization, and seal an immutable delivery. Format checks and generated files do not grant approval.

Persist the selected archive according to its Git/LFS policy only with Git authorization. Verify independent retrieval from the exact intended commit and remote. Create a publication plan for explicit ASC app/version/platform IDs, record separate human upload authorization bound to that plan, then export its handoff:

```sh
creative publication export --repo "$CREATIVE_REPO" --id "$CREATIVE_PUBLICATION_ID" --confirm
creative publication status --repo "$CREATIVE_REPO" --id "$CREATIVE_PUBLICATION_ID"
```

ASC executes authorized remote operations and supplies fresh evidence. Upload, processing, playback, and poster readiness are independent gates. Missing or contradictory evidence remains unproven. Creative never submits a version for review or uploads from CI.

For full commands and approval arguments, read the [operations guide](docs/artifact-operations.md), [storage relocation guide](docs/storage-relocation.md), and installed [lifecycle contract](plugins/app-store-creative/skills/app-store-creative/references/lifecycle-contract.md). Inventory and planned quarantine/restore/purge operations govern retention; unknown files are preserved.

## Repository validation

```sh
python3 -m unittest discover -s tests -q
python3 .github/validate_plugin.py
python3 .github/package_plugin.py --output /absolute/path/to/app-store-creative.zip
```

The package check extracts the complete plugin and runs its installed managed interface independently of the source checkout. Studio tests and its build run from `plugins/app-store-creative/studio`. Package checks and unit tests do not substitute for the two-product production and ASC acceptance required by ADR-002.

## License

MIT

To reuse an already registered capture without losing its acquisition provenance, import
its artifact identity and use the returned managed input path in the screenshot recipe:

```sh
app-store-creative input import --repo . --artifact <capture-id> --actor <actor>
```

`--artifact` and `--source` are mutually exclusive. Artifact imports require a complete
capture from a successful acquisition attempt and retain the original capture dependency.
