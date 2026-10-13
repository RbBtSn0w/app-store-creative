# Workflow Contract

The managed lifecycle contract is the sole authority for new work. Read [lifecycle-contract.md](lifecycle-contract.md) for record schemas and command details. Legacy release manifests, task stores, and command aliases are not accepted or migrated.

## Sources of truth

| Boundary | Authority |
| --- | --- |
| Recipe and storage | Project configuration and protected local storage layer |
| Work and dependencies | Immutable run, leased attempt, and artifact provenance |
| Product pixels | Real UI inputs and producer capture receipts |
| Editable composition | Declared source design and localized recipe |
| Local acceptance | Validation bound to the exact candidate and policy |
| Design acceptance | Explicit human approval bound to that candidate |
| Release evidence | Immutable delivery and verified archive manifest |
| Upload authorization | Separate human approval bound to the publication plan |
| Published truth | Bound observations from fresh App Store Connect reads |

## Ordered gates

1. Inspect the installed CLI, effective storage configuration, and proposed Git policy.
2. Import real product inputs and create independent managed production attempts.
3. Register screenshots, preview video, and poster with their provenance.
4. Validate the exact candidate and review the visual result.
5. Record explicit human design authorization and seal an immutable delivery.
6. Archive and prove independent retrieval from the intended Git commit and remote.
7. Bind a publication plan to explicit ASC app, version, platform, and resource IDs.
8. Record separate upload authorization for that exact plan and export its handoff.
9. Let the official ASC plugin execute the authorized upload and collect fresh observations.
10. Inspect each remote readiness gate; absent evidence remains unknown.

No downstream artifact retroactively proves an earlier gate. A successful command is not human approval. CI never uploads or submits a version for review. Creative prepares and evaluates evidence; ASC owns external execution.

Use the CLI help for current arguments. Never invent approval references, flatten media paths, or reinterpret existing records under changed storage roots.
