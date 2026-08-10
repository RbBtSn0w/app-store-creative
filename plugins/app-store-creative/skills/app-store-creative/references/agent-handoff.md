# Agent Handoff Contract

## Claim

Use the task ID from the generated plan. Claim it with a stable agent identity and a bounded lease. Do not work around another active claim.

```sh
python3 <plugin-root>/scripts/app_store_creative.py claim --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id> --ttl-seconds <seconds>
```

Before editing shared artifacts, read `status` again and verify all dependencies are complete. A lease grants task ownership, not permission to bypass release gates or mutate external systems.

Run state lives under `<repo>/.app-store-creative/`: task snapshots in `tasks/`, leases in `claims/`, durable handoffs in `receipts/`, approval records in `approvals/`, generated plans in `upload-plans/`, and append-only evidence in `events/`. Treat these as engine-owned records.

## Receipt

Write a machine-readable receipt that identifies:

- run, task, agent, UTC completion time, and source revision;
- exact inputs and their hashes;
- exact outputs and their hashes;
- tools and commands used, including relevant versions;
- validation performed and its result;
- unresolved warnings or manual boundaries.

Add role-specific evidence: capture checkpoint mapping, Figma frame IDs, video probe output, validation findings, or remote ASC identifiers.

Complete only with a durable receipt:

```sh
python3 <plugin-root>/scripts/app_store_creative.py complete --repo <repo> --run-id <run-id> --task-id <task-id> --agent-id <agent-id> --receipt <receipt-file>
```

If work fails, preserve useful evidence and leave the task resumable. Never fabricate a completion receipt to unblock the graph.
