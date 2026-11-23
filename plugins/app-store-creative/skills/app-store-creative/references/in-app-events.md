# In-App Events

Use the installed launcher at runtime/scripts/app-store-creative. Commands return JSON on stdout. Inspect findings on a nonzero exit. Use the eventKey within one project and App. Prefix or suffix the action with --repo. All inputs are resolved relative to that project.

## Candidate and validation

Start with runtime/assets/templates/events/maintenance.json for an ordinary update or walking-week.json for a timed experience. The walking example is synthetic. Copy that directory into the target project as events/, update the project ID, ASC App ID, build, dates, territories and localized copy, then supply actual product evidence and images. The machine-readable brief contract ships in runtime/schemas/event-brief.v1.schema.json.

Base each claim on the supplied release notes, content or tested build. For each factual claim include text, project-relative path and SHA-256 of the original bytes. An absent timed experience yields skip with reason. A timed activity missing its audience, action, build, evidence or decision yields defer. Review localized claims against those facts before handoff.

```sh
app-store-creative events plan --repo . --brief events/walking-week.json
app-store-creative events validate --repo . --event walking-week --inventory inventory.json --routes routes.json
app-store-creative events handoff --repo . --event walking-week
app-store-creative events observe --repo . --event walking-week --snapshot observation.json
app-store-creative events assess --repo . --event walking-week --store store.json --product product.json
```

Each result includes recordSha256 and an immutable project-relative artifact. Named files under .creative/events/<eventKey>/ expose the latest record. Handoff reopens all inputs, checks image bytes, reruns the rules and rejects a changed validation. FFmpeg and ffprobe must be on PATH for image validation. Review both compositions in their intended slot. Link to that review using an evidence reference in the brief. Additional login or subscription scenarios belong in additionalRouteScenarios.

## Input records

All inputs have numeric schemaVersion 1. Each evidence reference has path and sha256. UTF-8 JSON with duplicate keys is rejected. Use ISO timestamps with explicit offsets. Normalize ASC/UI field names and state strings when collecting the snapshot. Preserve raw receipts separately. A normalized report is an assertion by the evidence producer; verify the source against it before importing.

| Input | Shape and collection |
|---|---|
| inventory | appId, observedAt, complete (all pages fetched), territories (App storefronts), hasApprovedVersion, events array. Each event has eventId, referenceName, state; active entries include territories and schedule with publishAt/startAt/endAt and optional overrides keyed by territory. Use DRAFT, READY_FOR_REVIEW, WAITING_FOR_REVIEW, IN_REVIEW, APPROVED, SET_TO_PUBLISH, PUBLISHED, PAST, ARCHIVED, REJECTED. App-wide occupancy counts distinct event IDs, including preheat. The local freshness limit is 24 hours. Refresh again before any write. |
| routes | bundleId, buildRef, eventKey, deepLink, checks array. Each check has scenario, territory, eventKey, observedAt, actualDestination, passed, actionAvailable and evidence. Use cold, warm, onboarding, expired, plus preheat when applicable. Compare a stable UI identifier chosen by the app team and declared under destinations. For an XCResult bundle, export the screenshot or JSON attachment as the evidence file. |
| observation | appId, eventKey, handoffSha256, observedAt, evidence, complete, matches array. Complete means the Publisher fetched the entire requested scope. Use readStatus=forbidden, rate-limited, unavailable or write-unknown to record a failed read or uncertain write. A match contains eventId, state and actual referenceName, schedule, territories, deepLink, badge, purpose, priority, purchaseRequirement and primaryLocale. Drafts include localizations, an object keyed by locale. An empty object asserts a complete read returned no localizations. |
| remote localization | localizationId, text (name, shortDescription, longDescription), assets object keyed by card/details. Record assetId, state (PROCESSING/COMPLETE/FAILED) and verified sha256 for delivered bytes. Omit an absent slot only after reading it. If the API exposes no comparable digest, verify the retrieved bytes or leave digest unknown for manual verification. |
| remote submission | If present under the match, include submissionId, appId, platform, state, and the complete items list of type/id pairs. For a first version or requiresNewVersion, verify the brief's versionId. |
| store/product | source (store or product), appId, eventKey, bound eventId, territories, window=event_start_to_end, from/to (earliest regional start and latest end), availability, metrics, evidence. Use available, suppressed, delayed or not-collected. Unavailable metrics use an empty object. Product counts must be deduplicated on the declared cohort and report the exact cohort identifier. Store counts retain source units. |

## Publisher execution and recovery

The five commands operate on local files. Only the Publisher invokes remote tools within an existing authorization for the exact handoff hash, target and operation. Keep an intent record before each mutation with the authorized digest, operation, resource and timestamp. Preserve the ASC receipt or timeout outcome. Re-read and import an observation before deciding the next action. For static images the remote operations are asc app-events localizations create/update and asc app-events screenshots create. Verify the installed flags with --help. Use the separate card and details asset types from the handoff; operate on resolved localization IDs.

Before create, list all events for that app and compare the unique reference name and expected fields. Execute configureArgv as an argument array only after the initial read confirms absence and no outstanding create exists. For manual-required events configure the complete schedule and purchase requirement in ASC and read them back. After an uncertain create, an empty or ambiguous result stays pending-reconciliation. Resume using the verified ID. Never interpret the original create recipe as the next action after a timeout. For an existing event validate again after binding so the local inventory includes that event exactly once.

prepare-draft lists only missing resources. Re-read after creating a localization so uploads use its returned ID. await-delivery means wait for media processing. On a throttled read, honor Retry-After and use bounded retries; on forbidden check the selected account/app role. A new read cannot justify resending an uncertain mutation until the intended resource is reconciled. Review actions are suggestions subject to the user's exact submission authorization. For with-version route to the version release owner. A submission receipt is followed by a fresh state observation. Approved, scheduled and published are distinct observations.

## Device and result evidence

In the target App's XCUITest, launch into the required user state, open the deep link from a system surface (including first-launch onboarding), assert the accessibilityIdentifier for the expected activity, verify the activity-specific action and eventKey, then attach app.screenshot(). Repeat for each territory and phase. Test the actual distribution build's universal link on device during the pilot. An example assertion inside a test, after performing the system navigation:

```swift
let challenge = app.otherElements["walking-week.challenge"]
XCTAssertTrue(challenge.waitForExistence(timeout: 8))
XCTAssertTrue(challenge.buttons["walking-week.record-walk"].isHittable)
let evidence = XCTAttachment(screenshot: app.screenshot())
evidence.lifetime = .keepAlways
add(evidence)
```

For assessment read the policy from the sealed handoff. Supply either or both data sources. Missing Apple reporting and measured zero have separate representations. The ratio uses product counts in the stated cohort, and a minimum denominator applies before threshold comparison. A threshold result measures that cohort and window. Re-running with corrected reports retains preceding assessment records under their original digest.

When revising an existing brief from a prior read, pass its plan recordSha256 in --expected-plan. A concurrent edit produces a conflict. Report timestamps, cohort and territories must match the sealed policy. Store per-event values in their original units and supply aggregated product counts with auditable evidence.

The normalized input schema ships in runtime/schemas/event-inputs.v1.schema.json. Producers can select the inventory, routes, observation or report definition. Runtime checks also validate relationships, observation freshness and referenced files.
