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

The deprecated `assetDeliveryState` field can report `COMPLETE` while Apple has
not yet generated a playable video. Treat this as successful
file delivery, not proof that preview processing is complete.

After delivery, inspect the current preview resource through official ASC:

- Bind `sourceFileChecksum` to the approved local file and verify the configured
  poster-frame timecode.
- Prefer `videoDeliveryState` and `previewFrameImage` when the installed ASC CLI
  exposes them. Apple deprecated `assetDeliveryState` and `previewImage` in API
  3.7. A missing modern field is unknown, not success or failure. An empty legacy
  `previewImage` must not be treated as evidence that processing is pending.
- Verify the returned `videoUrl` is playable, with expected duration and valid
  video/audio streams. Report poster-image readiness separately. If modern image
  state is unavailable, retain that limitation; verify the acknowledged
  poster-frame timecode and inspect that interval in the approved video instead
  of indefinitely polling the deprecated image field.
- `asc video-previews download --id <preview-id> --output <new-local-path>` can
  verify that ASC exposes a playable URL when list output is incomplete. A
  `preview has no videoUrl` response means playback readiness remains unverified;
  do not retry the upload or regenerate the approved material for that reason.

Preserve the preview ID and poll that same asset with bounded, spaced reads.
Report delivery, video processing, and poster-image readiness separately. Do not
close the creative release while required playback readiness remains unverified.
Apple notes that preview processing can take up to 24 hours:
https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots


Apple's field migration reference:
https://developer.apple.com/documentation/appstoreconnectapi/app-store-connect-api-3-7-release-notes
