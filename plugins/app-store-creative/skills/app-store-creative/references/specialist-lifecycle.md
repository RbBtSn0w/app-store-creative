# Specialist Lifecycle Binding

Read [lifecycle-contract.md](lifecycle-contract.md). Capture, design, and preview production use the same core records; they do not own output roots, approvals, promotion, or retention policy.

1. Inspect `storage inspect` and the configuration authority. Start or receive a run with the target and current source hashes.
2. Start an attempt for the producer stage. Use its returned `work_path` for scratch work and preserve the current lease token. Renew long-running attempts; stop publishing artifacts when the lease expires. Recovery creates a new attempt with explicit reason.
3. Register source captures/takes/recipes as inputs. Register outputs using their input artifact IDs, media role, and portable logical path from the declared matrix. Register command/probe/acceptance receipts as evidence with the same dependencies. Keep raw product UI real and unchanged.
4. Register available partial outputs with `--partial` before recording failed/cancelled/interrupted termination, while the lease is valid. A partial artifact cannot be selected as final media. Preserve the original failure when ownership was already lost.
5. Finish the attempt, then select the exact ordered final artifact IDs and validate the candidate. Return run, attempt, artifacts, candidate, validation, and any gaps to the orchestrator. Do not invent human approval or ASC observations.

```sh
python3 <runtime-root>/scripts/app_store_creative.py attempt start --repo <repo> --run-id <run-id> --stage capture --owner <agent>
python3 <runtime-root>/scripts/app_store_creative.py artifact register --repo <repo> --attempt-id <attempt-id> --source <work-file> --role capture --logical-path sources/capture.png --lease-token <current-token>
python3 <runtime-root>/scripts/app_store_creative.py attempt finish --repo <repo> --id <attempt-id> --status succeeded --lease-token <current-token>
```

A final screenshot registration references its real capture input; a preview references real takes and the timeline recipe. An evidence artifact preserves exact commands, environment, revision, checkpoints/intervals, probes and reviewed frames. Keep credentials, lease tokens, personal data and host-specific paths out of formal portable evidence.

Use `preview record` and `preview produce` for managed native recording and timeline execution. Their adapters register media and producer evidence under leased attempts. Low-level executors are production components, not lifecycle clients; when invoking one explicitly, run inside the allocated work directory and register its files before selecting a candidate. Real product capture and complete execution identity still require the acceptance documented in the delivery audit. Retired task commands are not supported.
