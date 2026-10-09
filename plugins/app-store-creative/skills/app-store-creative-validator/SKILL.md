---
name: app-store-creative-validator
description: Validate App Store screenshot and App Preview artifacts, receipts, manifests, visual acceptance evidence, and upload readiness without mutating App Store Connect. Use before design approval, promotion, upload approval, or publishing, and when diagnosing missing locales, bad dimensions, alpha, color, naming, ordering, codec, duration, stale hashes, or incomplete provenance.
---

# App Store Creative Validator

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


Validate without changing media or mutating ASC. A passing validation never substitutes for human approval.

## Managed Candidate Validation

Read the [managed lifecycle contract](../app-store-creative/references/lifecycle-contract.md). New work validates an exact candidate through the shared core, which records immutable validation evidence. Check the declared media matrix, current source dependencies, artifact closure, and actual decoded media. Review visual quality and product authenticity separately. Return defects to the producing attempt and create a new candidate after repairs; never edit selected CAS bytes.

```sh
python3 <runtime-root>/scripts/app_store_creative.py candidate validate --repo <repo> --id <candidate-id>
python3 <runtime-root>/scripts/app_store_creative.py archive verify --repo <repo> --path <sealed-package> --expected-sha256 <manifest-sha256>
python3 <runtime-root>/scripts/app_store_creative.py publication status --repo <repo> --id <publication-id>
```

Missing, stale, or contradictory remote evidence remains unproven. The official ASC plugin performs fresh reads. A local media pass is not processing, playback, or poster readiness.

## Review

Read [validation.md](references/validation.md). Compare the candidate's selected artifacts with its declared media matrix, current inputs, hashes, dimensions, locale, order, and provenance. Inspect screenshots and preview acceptance frames for product authenticity and visual defects. Use the official ASC plugin for fresh remote reads. Return defects to their producing attempts and record a new candidate after repairs; validation never edits existing media or grants approval.

Poster media validation honors `previewVideo.posterRequired`. A present poster
must match the dimensions of a locally validated preview. Managed candidate
validation additionally requires the poster's exact selected-preview dependency;
filesystem validation alone cannot prove that identity relationship.
