# Featuring nominations

Ask which release, audience and user-visible change the developer wants to pitch. Inspect the actual release notes, screenshots or recording. Write a short editorial description in the requested language. Keep speculative benefits out of the copy. Review each material claim against its evidence and distinguish shipped behavior from future plans. Only include supplemental URLs the developer selected for Apple and confirmed are publicly accessible. The CLI validates URL syntax and local evidence integrity; the publisher checks actual shareability.

Save a brief in the consuming project. The local-only context and evidence stay in the review record. Use this shape, replacing the example statement with the actual source.

```json
{
  "schemaVersion": 1,
  "target": {"profileRef": "team", "appIds": ["123456789"]},
  "payload": {
    "name": "Offline trail guides",
    "type": "APP_ENHANCEMENTS",
    "description": "Riders can read saved route guides while offline.",
    "publishStartDate": "2027-05-01T08:00:00Z"
  },
  "context": {
    "release": "2.0",
    "claims": [{"text": "Saved guides work offline.", "evidenceIds": ["release-note"]}]
  },
  "evidence": [
    {"id": "release-note", "sourceKind": "statement", "actor": "release owner", "text": "Confirmed saved guides open in airplane mode on the release build."}
  ]
}
```

For a source file, provide id, sourceKind (file, releaseNotes, screenshot, or video), project-relative path and sha256. Screenshots also require card, device and locale. Videos require startMs and endMs within the probed media duration. For managed media, supply artifactId and sha256 in place of path. The CLI verifies the retained object and its producer dependencies. Omit unknown payload fields until the developer supplies them. Explicitly review why the release matters now and any unanswered questions in context.

```sh
creative nomination --repo "$REPO" draft --brief nomination.json
creative nomination --repo "$REPO" review --id "$ID" --format markdown
creative nomination --repo "$REPO" draft --brief nomination.json --id "$ID" --base "$REVISION_DIGEST"
creative nomination --repo "$REPO" plan --action save-draft --id "$ID"
creative nomination --repo "$REPO" authorize --plan "$PLAN" --actor "$ACTOR" --human-reference "$AUTHORIZATION"
creative nomination --repo "$REPO" execute --plan "$PLAN"
creative nomination --repo "$REPO" status --id "$ID"
```

Read the exact plan before authorization. Changes omitted from subsequent briefs preserve the remote value; review the plan's expected fields. For submission, create a fresh plan with --action submit and authorize that specific review. execute uses the specified ASC profile, reads the live baseline, claims the plan, runs its write once and reads the result. Repeated execute for a consumed plan returns already_claimed. Use status for its verified receipt. A nonzero write exit without a structured rejection can indicate an accepted write with a lost response. Use reconcile to read the original nomination.

```sh
creative nomination --repo "$REPO" reconcile --id "$ID"
creative nomination --repo "$REPO" reconcile --id "$ID" --remote-id "$REMOTE_ID"
```

For unknown creates, inspect the candidates, confirm the identity with the developer and repeat with --remote-id and --accept-baseline. For known drafts changed in ASC, inspect the observed and prior baseline and explicitly adopt with --accept-baseline before replanning. When an unresolved attempt has a remote mismatch, keep its evidence and investigate the exact write. An explicit JSON:API rejection ends the attempt; generate and authorize a new plan before retrying.

For an external publisher use claim instead of execute. Only the first claim returns the argv array and environment overrides. Apply both and consume the handoff once. Register the exact response bytes through observe --attempt ATTEMPT --response FILE --scope FILE. Scope contains projectId, profileRef, appIds, attemptId, planDigest (the digest part of PLAN), observedAt (RFC3339) and phase (ack, view or rejection). Use view with all three relationships shown by the built-in executor. Ack retains the mutation ID; view verifies delivery. Keep the original profile attached to all executor calls.
