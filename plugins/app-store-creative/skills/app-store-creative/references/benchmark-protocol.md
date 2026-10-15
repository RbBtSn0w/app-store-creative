# Empirical Release & Repeatability Benchmark Protocol

> **Reference**: [Issue #22](https://github.com/RbBtSn0w/app-store-creative/issues/22)  
> **Status**: Active Measurement Framework  
> **Target Cohort**: 3–5 distinct Apple platform applications (e.g. macOS productivity, iOS utility, visionOS spatial).

---

## 1. Objectives

Provide an empirical measurement framework for evaluating onboarding simplicity, default visual design quality, and repeat-release efficiency across diverse Apple platform projects.

---

## 2. Key Metrics & Measurement Schema

For each evaluated product release run, record metrics into `.creative/benchmarks/<product_slug>-<run_id>.json`:

```json
{
  "schema_version": 1,
  "product": {
    "id": "levelory",
    "platform": "MAC_OS",
    "locales_count": 9,
    "cards_per_target": 5
  },
  "metrics": {
    "time_to_first_valid_candidate_seconds": 184.2,
    "active_human_intervention_minutes": 4.5,
    "approval_gates_traversed": 2,
    "agent_token_cost": {
      "prompt_tokens": 42150,
      "completion_tokens": 3120,
      "tool_invocations": 14
    },
    "recovery_elapsed_seconds": 22.8,
    "blinded_visual_score": {
      "scale": "1-5",
      "typography_hierarchy": 4.5,
      "device_frame_fidelity": 4.8,
      "color_contrast_wcag": 5.0,
      "overall": 4.7
    }
  }
}
```

### Metrics Definitions

1. **`time_to_first_valid_candidate_seconds`**:
   - Wall-clock seconds elapsed from repository initialization to the first successful `app_store_creative.py candidate validate --id <candidate_id>`.
2. **`active_human_intervention_minutes`**:
   - Total minutes an operator spends editing `creative.config.json`, adjusting captures, or resolving validation failures.
3. **`approval_gates_traversed`**:
   - Count of explicit human approvals registered (standard minimum: 2 — design approval and publication upload approval).
4. **`agent_token_cost`**:
   - Prompt/completion token consumption and tool call count when executed by an autonomous coding agent.
5. **`recovery_elapsed_seconds`**:
   - Wall-clock seconds elapsed from the detection of an invalidated source/config failure to the first successful passing re-validation.
6. **`blinded_visual_score`**:
   - Blinded design evaluation comparing default Studio outputs against reference hand-crafted designs on a 1–5 scale.

---

## 3. Protocol Execution Stages

### Stage 1: Clean Onboarding
1. Clone the project repository.
2. Initialize `creative.config.json` with target dimensions and default theme.
3. Import real UI screenshots via `input import` or capture journeys.
4. Export assets, create Candidate 1, and execute full baseline validation:
   ```sh
   python3 <runtime-root>/scripts/app_store_creative.py candidate validate --repo <repo> --id <candidate_id>
   ```
5. Stop the `time_to_first_valid_candidate_seconds` timer immediately upon successful validation exit.

### Stage 2: Incremental Revision (Repeat Release)
1. Introduce a minor UI modification (e.g., updated hero screenshot or revised localized headline).
2. Execute export (`app_store_creative.py export --repo <repo>`) and record elapsed re-render time (evaluating full re-render performance).
3. Create a new candidate revision and verify that candidate metadata preserves unchanged asset hash provenance for unmodified targets/locales.

### Stage 3: Simulated Failure Recovery
1. Introduce an intentional defect (e.g., corrupt image dimensions or missing mandatory localized capture).
2. Execute candidate validation (`app_store_creative.py candidate validate --repo <repo> --id <candidate_id>`); start the `recovery_elapsed_seconds` timer upon observing validation failure exit.
3. Diagnose the defect from validation error diagnostics, apply the targeted fix, and re-run validation.
4. Stop the `recovery_elapsed_seconds` timer immediately upon receiving validation success (`exit code 0`).
