# PRD-001 implementation and acceptance evidence

Date: 2026-10-03. Baseline: `1f32d2c`. Status: **technical reference acceptance passed; product release gates remain open**.

## Implemented scope

Studio guides local project creation and opens existing projects. PNG/JPEG import preserves original bytes in content-addressed storage. Cards can be ordered, removed, edited, and assigned independent target/locale captures and composition. Localization inheritance requires explicit review.

Conditional saves reject stale writers, preserve backups, and atomically replace configuration. Edits made during a pending save remain dirty. Navigation warns about unsaved changes; drafts can be downloaded after operation errors.

Export uses saved configuration and source snapshots, stages outputs, and refuses publication when reviewed inputs change. Selected export checks the selected set; full verification checks the entire declared matrix. New projects require render evidence binding configuration, scoped source hashes, output hashes, and readiness. Legacy projects retain compatibility and display `Files checked` until reviewed rendering is enabled. Previous release-lock metadata is retained; previous bitmap versions are not archived.

Preview and export share composition, font readiness, image decoding, transformed bounds, clipping, and collision checks. Missing explicitly named fonts fail even when fallback exists. Verified status requires a current saved revision, complete evidence, and no outstanding edits or operation errors. Output links are discoverable in Studio. Canonical validation and ASC handoff retain existing ownership; no upload occurs.

## Executed checks

| Check | Observed result | Boundary |
| --- | --- | --- |
| Python regression suite | 73 passed | Transport, conditional saves, import integrity, isolation, source changes, render evidence and process ownership |
| Studio unit suite | 37 passed | Composition, localization, geometry, fonts, release state and escaped markup |
| TypeScript and production build | Passed | Bundled Studio rebuilt |
| Plugin metadata and complete package smoke | Passed | Version remains 0.2.10; no release |
| Production Chrome export | 24/24 PNG outputs; canonical validation PASS | macOS, Chrome 154.0.8037.97; synthetic reference |
| Output checks | Phone 1320×2868; Mac 2880×1800; no alpha; hashes recorded | All 24 assets |
| Preview/export geometry | All 24 match | Settled bounds normalized by width; tolerance 0.0025; exact text and line counts. Not pixel identity |
| Browser creation and JPEG import | Passed; stored bytes equal input | Synthetic capture 390×844 |
| Browser concurrent saves | Stale tab rejected; disk retains winning save and draft remains visible | Two actual tabs |
| Browser pending-save edits | Earlier snapshot saved; later edits remain dirty | Deliberately delayed test server |
| Browser localization and repair | Independent phone/Mac Chinese copy; English preserved; clipping/font warnings and repair observed | Font availability only; glyph coverage remains open |
| Browser full-matrix export | Button initiated all 24 outputs; completed with `Verified locally` and enabled controls | Latest Studio and server; actual production renderer |
| Browser release review | `Verified locally` and 24 output links observed | No remote upload claim |

The prior Chrome startup failure is resolved on the tested macOS path. Native application launch and real-time loopback CDP replaced the failing direct executable/virtual-time path. Rendering uses an isolated temporary profile and terminates only processes carrying that exact profile. Non-macOS rendering has not been verified in this acceptance run.

Production export, input/output hashes, geometry, and comparison results are recorded in [studio-reference-export-check.json](evidence/studio-reference-export-check.json). The older `studio-reference-render-check.json` is historical in-app-browser readiness evidence for an earlier configuration; it does not establish the current production export.

## Review fixes

An independent maximum-reasoning review identified two introduced defects. Default-language edits now update existing localized overrides so resolved copy/captures reflect the edit. Verification binds its starting configuration bytes, serializes with Studio writes, and rejects changes to configuration, sources (including reassigned symlink targets), outputs or render evidence before publishing a result. Regression tests demonstrated both failures before the fixes, then passed; all 73 Python and 37 Studio tests, type checking, build, metadata validation and complete packaging passed afterward.

## Outstanding product release gates

- Authorized real-product phone and desktop captures with independent English/Chinese states. The current six cards reuse four synthetic sources.
- Human visual review of real compositions, readability, intentional bleed, and background continuity. Geometry agreement does not establish design quality.
- Consented ten-participant study, original-workflow baseline, and follow-up. Completion, speed, satisfaction, conversion, and retention targets have not been measured.
- Broader glyph coverage, RTL, additional locales and platform compatibility remain later-scope work.

The unexecuted study procedure is documented in [PRD-001-pilot-protocol.md](PRD-001-pilot-protocol.md).

No commits, pushes, pull requests, remote uploads, or version changes were made. The complete PRD is not accepted solely from technical reference success.

## Reproduction

From the repository root:

```sh
python -m unittest discover -s tests
python .github/validate_plugin.py
python .github/package_plugin.py --output /tmp/app-store-creative-prd.zip
```

From `plugins/app-store-creative/studio`:

```sh
npm test
npx tsc --noEmit
npm run build
```

Use `tests/fixtures/studio_matrix.config.json` in an isolated consuming project with the four captures described in `tests/fixtures/README.md`. Run canonical export and validation, then inspect outputs. Never manufacture evidence records. Record runtime version and hashes for each acceptance run.
