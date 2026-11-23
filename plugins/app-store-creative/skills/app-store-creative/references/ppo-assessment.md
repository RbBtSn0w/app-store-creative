# Run a measured screenshot experiment

Use one falsifiable question, the original page and a specific creative change. For example, an app can compare showing “search saved content” first against showing “save content” first. Select the minimum useful relative conversion lift before launch. Preserve the App Analytics observation as a separate file so another operator can check the transcription.

## Prepare the handoff

Example experiment inside creative.config.json. The project must declare the listed locale, target and both card IDs. An experiment can cover multiple locales and targets. The days and lift below illustrate the format.

```json
{
  "name": "Search first", "platform": "IOS", "trafficProportion": 50,
  "hypothesis": "Showing a search result first improves download conversion",
  "policy": {
    "testedChange": "Swap the save and search screenshots",
    "locales": ["en-US"], "targets": ["iphone_6_9"],
    "minRelativeLiftPct": 5, "durationEstimateDays": 30,
    "estimateSource": "ASC duration estimate recorded before launch"
  },
  "treatments": {"B": {"name": "Search first", "cardOrder": ["search", "save"]}}
}
```

Replace the example estimates with observations. An unknown estimate may be omitted. For historical exploration without a previously agreed threshold, omit minRelativeLiftPct. A prior hypothesis recorded after seeing the results is exploratory. Read the preflight before using traffic. Prepare and seal the original and treatment screenshots through the existing production and delivery workflow. Use a different handoff filename when replacing a draft with a sealed run.

Commands below use the existing creative launcher and run from the product repository.

```sh
creative ppo plan --experiment first
creative ppo handoff --experiment first --baseline-delivery "$ORIGINAL_DELIVERY" \
  --treatment-delivery "B:$B_DELIVERY" --output ppo/handoff.json
```

The publisher checks the actual screenshot order for each locale and device in App Store Connect. Review, start and online application follow the existing publisher workflow. Bind only after verifying the real App Store app, experiment and treatment IDs against those pages. The original page uses the reserved identity original. Bind repeated --treatment-id values for separate variants. Identical repeats are safe; use a new filename for a new deployment.

```sh
creative ppo bind --handoff ppo/handoff.json --app-id "$ASC_APP_ID" \
  --asc-experiment-id "$ASC_EXPERIMENT_ID" --treatment-id "B:$ASC_TREATMENT_ID" \
  --output ppo/binding.json
```

## Capture and assess an observation

Retain the App Analytics table or screenshot locally. Record Apple’s displayed estimates and the baseline actually selected. For an unfinished experiment set state to running. Use ended only after verifying the remote state. Use null for unavailable measures. Scope must match the reviewed experiment and evidence. If Apple shows aggregate performance, describe the lift for the aggregate. Do not infer device- or language-specific lift from that table.

Synthetic snapshot template. Replace placeholders and example metrics with the values from the same observation. Use SHA-256 of the original file bytes (on macOS, shasum -a 256 FILE).

```json
{
  "schema_version": 1, "binding_sha256": "<binding file digest>",
  "app_id": "<ASC app ID>", "experiment_id": "<ASC experiment ID>",
  "scope": {"locales": ["en-US"], "targets": ["iphone_6_9"]},
  "source": "ppo/apple-results.png", "source_sha256": "<source file digest>",
  "observed_at": "2026-11-23T08:00:00Z", "state": "ended", "baseline": "original",
  "rows": [
    {"treatment_id": "original", "apple_status": "Original", "unique_impressions": 10000,
     "conversion_rate_pct": 20, "relative_lift_pct": null, "confidence_pct": null},
    {"treatment_id": "<ASC treatment ID>", "apple_status": "Performing Better",
     "unique_impressions": 10000, "conversion_rate_pct": 21.2,
     "relative_lift_pct": 6, "confidence_pct": 93}
  ]
}
```

```sh
creative ppo assess --handoff ppo/handoff.json --binding ppo/binding.json \
  --snapshot ppo/snapshot-01.json --output ppo/assessment-01.json
creative ppo result --handoff ppo/handoff.json --assessment ppo/assessment-01.json \
  --output ppo/result.json
creative ppo reproduce --experiment first --result ppo/result.json --json
```

Assess prints JSON and writes only when given --output. Preserve each observation at a distinct filename. The result references input paths relative to the repository and verifies their bytes on replay. A newer observation uses a new snapshot and assessment path; a conflicting existing decision cannot be overwritten. Supply the specific evidence to replay rather than assuming the latest file by directory order.

| Action | Operator or agent action |
|---|---|
| wait | Revisit when new data arrives. |
| needs-review | Check the stated baseline, conflicting metrics or tied qualifying variants. |
| inconclusive | Keep the observed limitations in the experiment record. |
| keep-control | Keep the original page and record the business threshold and observation. |
| use-treatment | Preview the selected delivery, screenshot order, scope and evidence. Add --execute to render a local candidate. |

Measured reproduction uses the sealed recipe inputs and checks the scoped screenshot bytes against the measured archive. A mismatch leaves a failed production attempt. The normal approval, delivery and remote application steps remain separate. Older manual results and explicit --variant selection still use the existing workflow.
