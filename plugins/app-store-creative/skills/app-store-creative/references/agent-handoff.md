# Agent Handoff Contract

## Ownership

Read the [lifecycle contract](lifecycle-contract.md) and current run status before working. Start an independent attempt with a stable owner and bounded lease. Do not bypass another active lease. Renewal and recovery require the recorded token or an explicit recovery operation; a lease does not authorize approval, Git publication, or external mutation.

```sh
python3 <runtime-root>/scripts/app_store_creative.py run status --repo <repo> --id <run-id>
python3 <runtime-root>/scripts/app_store_creative.py attempt start --repo <repo> --run-id <run-id> --stage <stage> --owner <agent-id>
```

## Production evidence

Register real inputs and outputs against the active attempt and lease token. Retain producer versions, source revision, input hashes, output hashes, locale, geometry, capture checkpoints, Figma frame identifiers, and preview intervals as applicable. Register producer evidence as an artifact and bind actual input artifact IDs; matching filenames do not prove dependency identity.

```sh
python3 <runtime-root>/scripts/app_store_creative.py artifact register --repo <repo> --attempt-id <attempt-id> --source <output-file> --role <role> --logical-path <media-path> --input <input-artifact-id> --lease-token <token>
python3 <runtime-root>/scripts/app_store_creative.py attempt finish --repo <repo> --id <attempt-id> --status succeeded --lease-token <token>
```

Finish failed, cancelled, or interrupted work truthfully and retain useful partial evidence. Retry in a new attempt; never overwrite previous outputs or fabricate completion to unblock downstream work. The candidate, validation, approval, delivery, and publication records remain separate gates. Storage locations come from the effective configuration rather than a fixed hidden directory.


## Executor receipt custody

Use the publisher's [original receipt custody workflow](../../app-store-creative-publisher/SKILL.md#original-receipt-custody) after registering remote observations. Report observation ID, retained evidence ID, immutable backend version, locator identity and independent retrieval evidence separately. Keep raw receipts and access paths private; do not attach them to public Git or treat a response hash as proof of long-term retrieval. Preserve uncertain requests and failed attempts for reconciliation before another request. Evidence retention never grants approval or triggers another ASC upload.
