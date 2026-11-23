# Custom product page workflow

Use the installed runtime's app_store_creative.py entry point. All paths below are relative to the product repository. Select truthful input from the current release and actual page inventory. The examples illustrate file shapes; replace every example identifier and hash with observed values.

## Prepare the campaign

Create .creative/cpp/share-save/brief.json, inventory.json and proposal.json. The campaign key, app ID and bundle must identify this project. Store release evidence, review media and sanitized ASC observations as local files inside the project; a reference consists of path and SHA-256 of the actual file bytes. For managed media outside the repository use a verified review copy, retaining its sealed artifact ID. Each role is screenshot or preview. PNGs must match the supported target. For a preview, validation is a file reference to the managed validation record containing the selected SHA-256 and a passing video entry. An optional poster reference includes path, sha256 and previewSha256; preview and Studio display that bound poster. The publication gates verify processing, playback and poster separately.

```json
{
  "schemaVersion": 1, "campaignKey": "share-save", "appId": "123", "bundleId": "example.clip",
  "platform": "IOS", "audience": "Tutorial readers", "channel": "Share tutorial",
  "intent": "Save incoming text", "locales": ["en-US"], "targets": ["iphone_6_9"],
  "releaseEvidence": {"path": "proof/release.txt", "sha256": "<release hash>"}
}
```

```json
{
  "schemaVersion": 1, "appId": "123", "bundleId": "example.clip",
  "observedAt": "2026-11-23T09:00:00Z", "complete": true,
  "defaultPage": {"localizations": {"en-US": {"promotionalText": "Find saved text", "media": {"iphone_6_9": ["search"]}}}},
  "pages": [], "approvedKeywords": {"en-US": ["clipboard"]},
  "assets": {
    "share": {"path": "proof/share.png", "sha256": "<sha>", "artifactId": "<sealed artifact id>", "role": "screenshot", "locale": "en-US", "target": "iphone_6_9"},
    "search": {"path": "proof/search.png", "sha256": "<sha>", "artifactId": "<sealed artifact id>", "role": "screenshot", "locale": "en-US", "target": "iphone_6_9"}
  },
  "evidence": {"share-in": {"path": "proof/share-in.txt", "sha256": "<sha>", "releaseSha256": "<release hash>", "supports": ["Save incoming text"]}}
}
```

Run cpp discover --app APP_ID to read all pages, their versions and localizations through authenticated ASC list operations. Use the returned parent-scoped resources and verified media observations to prepare inventory.json. Populate each pages entry with pageId, name, approved, visible, url and localizations in the defaultPage shape. Set complete only after the final pagination cursor. In evidence.supports include only claims the linked evidence actually demonstrates. For a deepLink add a matching routes entry in inventory with path, sha256 and releaseSha256 identifying the verified release route.

```json
{
  "schemaVersion": 1, "decision": "createPage", "name": "Share Save",
  "rationale": "Tutorial readers need a share-specific landing URL and the default page opens with search.",
  "claims": [{"text": "Save incoming text", "evidenceRefs": ["share-in"]}],
  "localizations": {"en-US": {"promotionalText": "Save incoming text", "keywords": ["clipboard"], "media": {"iphone_6_9": ["share", "search"]}}}
}
```

Select reuseDefault, reusePage, updatePage, createPage or needsEvidence based on the inventory. Existing CPP selections require pageId. Record gaps explicitly. Reuse decisions return the selected link. Omitted text, keywords or device media inherit the comparison page for that locale. Pass explicit ordered media for a replacement.

```sh
app_store_creative.py cpp plan --campaign share-save > plan.json
app_store_creative.py cpp preview --campaign share-save --plan plan.json --out review-v1/
app_store_creative.py cpp handoff --campaign share-save --plan plan.json --out prepare.json
```

Studio's approval workspace lists campaigns and opens the same visual comparison. Reordering writes proposal.json with revision checks. Regenerate the plan and choose a new output location after edits. Blocked decisions return exit code 3; invalid input returns 2.

## Execute and recover

resolveDraft identifies the page preparation/readback needed. Creating a page through asc product-pages custom-pages create also creates its first version and primary localization. Record the result before scheduling additional localizations. A local handoff or claim records intent; the existing human-approved Publisher/ASC executor performs authorized writes. Use one shared campaign workspace for execution.

Populate observation.json beside brief.json with campaignKey, appId, bundleId, pageId, pageVersionId, planDigest, observedAt and an evidence file reference. The referenced file is the executor's normalized snapshot with this structure. Preserve original ASC responses separately for upload evidence. Verify parent links from ASC before normalizing.

```json
{
  "appId": "123", "bundleId": "example.clip",
  "page": {"pageId": "P", "name": "Share Save", "visible": false, "approved": false, "url": ""},
  "version": {"pageId": "P", "pageVersionId": "V", "state": "PREPARE_FOR_SUBMISSION", "deepLink": null,
    "localizations": {"en-US": {"localizationId": "L", "pageVersionId": "V", "promotionalText": "",
      "keywords": [], "media": {"iphone_6_9": []}}}}
}
```

media stores ordered verified SHA-256 digests. For existing remote media include setIds[device] keyed by screenshot and/or preview, using the actual remote media set IDs. Populate from matched remote assets using sealed bytes and verified checksums. Omit a device key only after verifying its set is empty. Unknown identity or incomplete media inventory requires evidence before execution. For matched assets supply readiness[device][assetSha256] with independently observed upload, processing and media booleans, plus poster for previews. Missing evidence produces verifyMedia. Evaluate state and app relationships immediately before each external mutation.

1. Generate handoff from the exact plan and fresh observation. Before each authorized operation run cpp claim --campaign KEY --plan PLAN --operation ID. Proceed only for a newly reserved result. For reconcileMedia write its scope as a JSON target and run the existing publication plan, approve-upload and export commands for the matching sealed delivery. Verify exact replacement/deletion effects and remote set IDs before acting.
2. Bind the resulting normalized observation to the original plan, then run cpp reconcile --campaign KEY --plan PLAN --operation ID. If the executor crashed, refresh ASC first. A pending claim blocks a second external operation; an unknown outcome stays pending until resolved by evidence. An HTTP 409 requires state refresh; honor Retry-After on 429 and diagnose credentials on 401/403.
3. Re-run handoff with a new output filename. Matching operations disappear. reviewHandoff identifies the CPP version for manual submission; obtain screenshot and preview readiness evidence before submission. For an approved page update, supply a completely paginated versionInventory array in the snapshot, with pageVersionId and state for each version. A new draft is only proposed after existing versions have been reconciled. An approved older version can remain visible during new review. cpp status reports page URL separately from the observed version state. Confirm the URL in the intended storefront before distributing it.
4. For CPP media normalization the executor supplies localizationId (or customProductPageLocalizationId) and sets in the supported media-list envelope, with the original response bytes retained as evidence where the upstream shape is supported. An unsupported response requires a new explicit adapter or separately bound observation.

## Import acquisition reports

Export daily **detailed** App Store Downloads and Discovery and Engagement segments as TSV or TSV.GZ. Provide a manifest.json in the input directory. Each revision describes the complete authoritative segment set for its report and day. Merge late-arriving batches into that set before incrementing revision. Segment paths are relative to the manifest. Record page title validity periods for every page that used the same name.

```json
{
  "appId": "123", "granularity": "daily",
  "pageNames": [{"pageId": "P", "title": "Share Save", "from": "2026-11-01", "to": "2026-11-30"}],
  "instances": [{"type": "downloads", "date": "2026-11-23", "revision": 1,
    "segments": [{"path": "downloads.tsv.gz", "sha256": "<segment hash>"}]}]
}
```

Use type discovery for page-view data. Run cpp report --campaign KEY --input reports --from YYYY-MM-DD --to YYYY-MM-DD. Results preserve source, date, device, territory and observed counts. Missing rows are unknown. A conversion rate requires comparable deduplicated visitor data; these report slices do not supply that denominator.
