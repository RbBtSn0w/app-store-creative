# App Store Connect Recovery

## Before writing

Use the official ASC plugin and resolve IDs from a fresh remote read. Confirm app, version, platform, localization, screenshot display type, and preview set. Compare the upload plan hash with the upload approval. Refuse CI or an expired/mismatched approval.

The local engine `upload` command is a dry-run gate and performs no ASC mutation. After it passes, translate only the approved plan operations through the official ASC plugin.

## Partial failure

1. Stop broad retries.
2. Read remote state again and identify exactly which locale and media items succeeded.
3. Preserve local promoted assets and hashes; do not regenerate them during recovery.
4. Repair the smallest failing boundary, such as one locale, ordering operation, or preview set.
5. Rebuild the plan if remote state changed; obtain a new upload approval when plan content changes.
6. Retry only unresolved operations, then run a fresh audit.

Do not delete the old remote set until verified replacements are locally available and the approved plan explicitly requires replacement. Never infer rollback from a client error: the server may have accepted part of the request.

## Completion report

Report the approved local plan, attempted operations, successful writes, failed or skipped operations, and fresh remote state independently. Upload completion does not authorize submitting the app version for review or changing release settings.
