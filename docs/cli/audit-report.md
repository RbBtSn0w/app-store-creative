# `audit report`

Export a Markdown provenance audit report for a lifecycle run.

## Usage

```sh
app_store_creative.py audit --repo /path/to/product report --run-id <RUN_ID>
```

## Output

The report is summary-first:

1. Run ID, generation time, and a machine-checkable integrity line:
   `artifacts=N receipts=N candidates=N approvals=N gaps=N`.
2. A gap table listing partial artifacts, integrity failures, missing
   producer receipts, missing or stale design approvals, and discarded
   candidates.
3. Artifact inventory with role, logical path, SHA-256 prefix, size,
   integrity, producer attempt, input lineage, and experiment provenance
   when present.
4. Receipt table showing which artifacts consumed each producer-evidence
   receipt.
5. Design approval references with actor and binding status.
6. Delivery references with revalidated local status via
   `delivery_status()`.
7. Publication references.

The report is read-only; it does not create or modify lifecycle records.
