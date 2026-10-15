# Automated GitHub releases

The main push CI validates the plugin, Python suite, Studio tests/types/build,
isolated distribution, and release tooling before running semantic-release.
Pull requests validate tooling but cannot publish. Releases are serialized per
branch; failed validation prevents release. Node 24 runs the locked release tools.

Conventional Commits determine the version relative to the last reachable `v*`
tag: `fix:` produces a patch, `feat:` a minor, and a `BREAKING CHANGE:` footer a
major. Documentation and maintenance commits alone do not release. Use conventional
PR titles when squash merging; regular merges retain the individual commit messages.
The existing `v0.1.0` tag is the initial baseline. The first automated version is
computed from all subsequent commits, not from the proposed `0.3.0` release notes
or the source manifest. Do not create a baseline tag for an unpublished version.

The validation job preserves its freshly built and smoke-tested ZIP as an immutable
Actions artifact named for the triggering SHA. The release job downloads that
artifact from the same workflow run instead of using the checkout's tracked Studio
build. Missing artifacts fail the release rather than falling back to source.
The prepare hook copies that validated plugin into temporary staging, stamps both
plugin manifests with the calculated version while preserving their other bytes,
including whitespace and nested version properties, and runs the existing isolated
package smoke checks. It also updates the repository's source manifests in place so
`@semantic-release/git` commits and pushes the updated manifests back to `main` with
`[skip ci]`. GitHub receives `app-store-creative.zip` and generated release notes.
Both the source manifests on `main` and the release ZIP stay aligned with the released
version. No npm package, ADG update, or ASC operation is performed.

When configured with `vars.RELEASE_BOT_APP_ID` and `secrets.RELEASE_BOT_PRIVATE_KEY`,
the release job mints an installation token for `rbbtsn0w-bot` using `actions/create-github-app-token@v3`
to bypass repository rulesets (such as required pull requests on `main`) and publish
release commits and tags. If absent, it falls back to the default `github.token`.
The release checkout does not persist credentials, release tooling installs with
lifecycle scripts disabled, and only the publish step receives the release token.

Dependency audit at integration reported 12 transitive advisories (10 high,
2 moderate) even with semantic-release 25.0.9. Compatible `npm audit fix` did not
resolve them: several are bundled inside the unused npm publishing plugin, and
the active commit-analysis path includes `micromatch`/`braces`. Do not use
`npm audit fix --force`, whose proposed downgrade is semantic-release 15.
Track upstream fixes and review dependency updates before enabling production
releases. The locked toolchain is not claimed to be vulnerability-free.

Local verification:

```sh
npm ci --ignore-scripts
npm run test:release
npm run release -- --dry-run
```

The dry run requires GitHub credentials and remote access, verifies push permission,
and skips prepare/publish. It does not validate ZIP creation. To check preparation
without publishing, run the local prepare hook with a stable test version:

```sh
python3 .github/package_plugin.py --output .build/validated/app-store-creative.zip
python3 -m zipfile -e .build/validated/app-store-creative.zip .build/validated
node -e 'require("./.github/release.cjs").prepare({}, {cwd: process.cwd(), nextRelease: {version: "0.3.0"}})'
```

If publishing fails after creating a tag, inspect the Actions logs, tag SHA and
GitHub assets before recovery. A rerun may find no new commits and does not guarantee
repair of a partial release; never move or delete the tag automatically.
