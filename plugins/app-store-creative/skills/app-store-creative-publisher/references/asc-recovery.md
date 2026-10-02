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


## Preview delivery versus video processing

A preview upload can report `assetDeliveryState.state: COMPLETE` while Apple has
not yet generated its playable video or poster image. Treat this as successful
file delivery, not proof that preview processing is complete.

After delivery, inspect the current preview resource through official ASC:

- Bind `sourceFileChecksum` to the approved local file and verify the configured
  poster-frame timecode.
- Inspect `videoDeliveryState` and `previewFrameImage` when the installed ASC CLI
  exposes them. A missing field is unknown, not success.
- Check for a nonempty playable `videoUrl` and a generated preview image. An empty
  image template with zero dimensions is not visual acceptance evidence.
- `asc video-previews download --id <preview-id> --output <new-local-path>` can
  verify that ASC exposes a playable URL when list output is incomplete. A
  `preview has no videoUrl` response means playback readiness remains unverified;
  do not retry the upload or regenerate the approved material for that reason.

Preserve the preview ID and poll that same asset with bounded, spaced reads.
Report delivery, video processing, and poster-image readiness separately. Do not
close the creative release while required playback readiness remains unverified.
Apple notes that preview processing can take up to 24 hours:
https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots
