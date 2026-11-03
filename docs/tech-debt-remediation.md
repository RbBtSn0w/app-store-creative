# Technical debt remediation — 2026-11-02

This change addresses the six findings audited from source baseline `90f2aec`.
The final local verification results and source fingerprints are recorded in
[the verification receipt](evidence/tech-debt-remediation-2026-11-02.json).
Local results do not establish a successful remote Actions run or a product release.

## Verified result

All six findings are implemented and locally verified. The four ordinary Python
shards executed 1,322 tests: 1,288 passed and 34 skipped. The dedicated real-volume
suite separately executed all 33 cross-filesystem cases with zero skips and
successfully unmounted its owned volume. One explicitly authorized native-window
recording case remains skipped. Studio passed 131 tests, type checking and a clean
locked-install production build. Release tooling passed four tests, and actionlint
accepted the workflow. The [combined local summary](evidence/tech-debt-test-summary-2026-11-02.md)
passed with required cross-filesystem evidence.

The initial concurrent run encountered a loopback port collision and 5/30-second
timeouts. A serial attempt also encountered two 5-second HTTP timeouts during
severe host saturation. Failures are retained in the receipt. The same two cases
passed against both isolated baseline and current sources without changing their
deadlines; the complete affected shards then passed. Verification input hashes
remained unchanged throughout. These observations support a transient environment
explanation, not a proven single root cause or a relaxed gate.

The independently extracted plugin produced an actual Chrome screenshot, a
15-second FFmpeg preview and its poster, validated their candidate, sealed a test
approval, and restored 18 files independently. Recipe bytes were unchanged, and
the source/installed runtime fingerprints matched. The synthetic browser project
also passed target-copy isolation, delayed-GET preservation and reopening checks;
see the [browser screenshot](evidence/tech-debt-browser-acceptance-2026-11-02.jpg).

## Behavior and boundaries

- Default-language edits update the effective field owner: an explicit locale
  override, an existing target override, or shared copy. Empty target copy remains
  explicit. Editing a target override preserves shared copy and other targets.
- Review notes use one state model for loading, editing, saving and the unsaved
  changes warning. Session-touched cards reject late initial data even after a
  successful save. Edit sequences prevent an earlier save from clearing newer
  edits, including edits that restore identical text. Invalidated effects cannot
  apply old loads or save completions.
- Atomic JSON serializes before creating a temporary file. Write, close and
  replacement failures clean up only the temporary inode owned by the operation;
  substituted files and the original target remain protected.
- `record_primitives` owns canonical bytes, file digests, record identities, time
  and dependency traversal. `storage_paths` owns storage root resolution and
  workspace paths. Their implementations are unchanged; `artifact_lifecycle`
  reexports the original names. Internal consumers import foundations directly.
  Both modules are required installation payloads. New source fingerprints are
  expected; historical production records are not rewritten.

## Continuous validation

Studio tests, TypeScript checks and production build precede a Git-based dist
freshness check. The check compares against `HEAD` and includes ignored and
untracked files, additions, deletions and modifications. It intentionally rejects
locally rebuilt assets until the matching source and generated assets are part of
the same commit. The initial validation was performed before staging; the follow-up submission is separately authorized.

Every PR and main push runs a separate real-volume job on `macos-15`. It creates
an owned 1 GiB APFS sparse image, verifies a different filesystem device, and runs
the cross-filesystem suites with `--fail-on-skip`. The 300-second per-test watchdog
and a 600-second whole-suite deadline bound execution. A zero-test suite or any
skip fails this job. Ordinary unit shards retain their existing skip policy.

The harness records directory and image inode identities and verifies the exact
image/device association before detaching. System path aliases are canonicalized.
Failure and interruption cleanup is followed by an always-running retry step;
malformed test evidence must not prevent cleanup from valid ownership state.
Cleanup failure remains a failed gate, with the owned state retained for retry.

The combined summary consumes a separate cross-filesystem artifact, checks the
current workflow source/run context, and leads with the combined verdict. Missing
reports, explicit unsuccessful shards, unexpected successes and cleanup failures
cannot produce a passing required summary. Publishing depends on all validation
jobs and the summary job.

## Reproduction

Run each ordinary shard (1 through 4) with the repository's standard runner:

```sh
python3 .github/run_sharded_tests.py --shard 1 --total 4 --report /tmp/creative-shard-1.json
python3 .github/validate_plugin.py
python3 .github/package_plugin.py --output /tmp/app-store-creative.zip
npm run test:release
```

From the Studio directory:

```sh
npm ci
npm test
npx tsc --noEmit
npm run build
```

On a macOS host that permits local disk images, use a fresh state location for
each run and always execute cleanup:

```sh
CREATIVE_CHECK_DIR="$(mktemp -d)"
trap 'python3 .github/run_crossfs_tests.py cleanup --state "$CREATIVE_CHECK_DIR/state.json" --report "$CREATIVE_CHECK_DIR/crossfs.json"' EXIT
python3 .github/run_crossfs_tests.py run --state "$CREATIVE_CHECK_DIR/state.json" --report "$CREATIVE_CHECK_DIR/crossfs.json"
```

Browser acceptance uses an isolated synthetic project. Hold the initial critique
GET response, edit and save a note, then release the captured old response. The
new note must remain visible and survive reopening. Edit a target-only title and
check both the saved target value and unchanged shared value. State tests also
cover intentional clearing, interleaved cards, in-flight saves and stale effects.

Installed media acceptance uses actual Chrome rendering and FFmpeg on synthetic
inputs, a clearly identified test approval, and external temporary storage roots.
It validates screenshot/video/poster selection, sealing and independent restore.
It does not establish real-product capture, human design approval, ASC readiness,
upload, App Review or release acceptance.

## Review cleanup follow-up

The review follow-up always reaps the owned test process group, including workers
left behind by an exited leader. State persistence errors retain a failed verdict
while verified detachment and cleanup still proceed; result evidence is written
even when final state persistence fails. Three permanent regressions cover these
paths. The focused runner/report/lifecycle suite passed 37 tests, and the real
APFS suite passed all 33 cases with zero skips and successful cleanup. Package
smoke and actionlint passed. The earlier full Python result remains scoped to its
recorded source hashes; remote PR CI validates the combined revision.

## PR 62 review follow-up

The summary now preserves the original setup failure when cross-filesystem tests
never started, together with cleanup status and any cleanup error. Critique save
feedback distinguishes the submitted notes from newer unsynced edits and only
confirms completion for the saved card's clean draft.

The initial PR CI run failed nine subcases in the simulated volume lifecycle:
its partial stat replacement omitted `st_mode`, which Python 3.12 path checks
require. Python 3.10 reproduced the same failure locally. The fixture now retains
the complete stat result while changing only the simulated device number; no
production cleanup checks or timeouts were weakened. All 16 distribution-gate
tests pass on Python 3.10 and 3.14. The surrounding report and runner suites pass
22 tests. Studio passes 132 tests, TypeScript checking and production build;
the generated distribution is included. Remote CI validates Python 3.12 and the
combined revision.

The subsequent review also scopes critique notices to their card in the draft
state. Saving or copying another card cannot overwrite an earlier card's unsynced
notice, and editing clears only that card's notice. Session guards reject stale
notice callbacks. A multi-card regression covers these transitions; Studio now
passes 133 tests plus TypeScript checking and production build.
