# Workflow Contract

## Sources of truth

| Boundary | Authority |
| --- | --- |
| Work and dependencies | Generated run plan |
| Product pixels | Named E2E/UI recordings and capture receipts |
| Editable screenshot layout | Official Figma file identified by the repository manifest |
| Copy and release policy | Repository manifest and localized copy files |
| Media requirements | Repository manifest plus current App Store Connect constraints |
| Design acceptance | Explicit `design` approval bound to an input manifest |
| Upload authorization | Separate explicit `upload` approval bound to the upload plan |
| Local release evidence | Promoted manifest, hashes, validation report, and receipts |
| Published truth | Fresh read from App Store Connect |

## Ordered gates

1. `doctor` passes and dependencies are available.
2. `plan` creates the run graph.
3. Capture receipts prove authentic UI inputs.
4. Figma screenshot exports and real-UI preview videos are complete.
5. `verify`, media probes, acceptance snapshots, and visual review pass.
6. A human records design approval.
7. `promote` produces immutable release evidence.
8. `upload-plan` is reconciled with current ASC state.
9. A human records a distinct upload approval for that exact plan.
10. A local, interactive publisher uploads; CI never uploads.
11. The engine's local-only `audit` confirms receipt and event-chain integrity.
12. A separate fresh ASC read confirms remote order and completeness.

No downstream artifact retroactively proves an earlier gate. Never treat a successful command as equivalent to a human approval.

## Approval commands

```sh
python3 <plugin-root>/scripts/app_store_creative.py approve --repo <repo> --release <version> --stage design --approved-by <identity> --input-manifest <manifest-file> --confirm APPROVE
python3 <plugin-root>/scripts/app_store_creative.py promote --repo <repo> --release <release.json> --input-dir <validated-export-root> --confirm-approved PROMOTE
```

The validated export root must preserve each task's relative `output` path.
Never flatten locale or device directories: duplicate basenames are valid.

Request upload approval later, against the generated upload plan. The publisher must not submit the app version for review.
