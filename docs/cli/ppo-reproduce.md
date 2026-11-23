# `ppo reproduce`

Reproduce a winning experiment variant into production deliveries.

## Usage

```sh
app_store_creative.py ppo --repo /path/to/product reproduce \
  --experiment <EXPERIMENT_ID> \
  --variant <TREATMENT_ID> \
  [--decision-basis "winner selected in ASC on 2026-10-19"] \
  [--execute] [--json]
```

## Modes

- **Dry-run (default):** emits a review plan with provenance header,
  treatment storage namespace, locale/target scope and planned delivery
  count. No storage is written.
- **`--execute`:** derives the treatment configuration (per-treatment
  workspace namespace), runs the existing managed production pipeline and
  attaches the provenance block (experiment ID, variant ID, decision basis)
  to every registered artifact receipt.

## Notes

- Use `--result PATH` to reproduce a recorded selection. An assessed result replays the evidence, restricts the scope and verifies the rendered screenshot bytes. See the [measured PPO workflow](../../plugins/app-store-creative/skills/app-store-creative/references/ppo-assessment.md).
- Partial-failure semantics follow the existing production pipeline: any
  failure marks the run attempt failed and does not complete the delivery.
- All provenance fields survive the lifecycle record round-trip and appear
  in `audit report` output.
