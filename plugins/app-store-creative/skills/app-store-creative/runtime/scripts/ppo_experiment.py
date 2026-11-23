#!/usr/bin/env python3
"""Product Page Optimization (PPO) experiment engine and ASC handoff compiler.

Provides declarative experiment definitions, treatment configuration derivation,
platform readiness validation, and authoritative ASC PPO handoff manifest generation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ppo_assessment as assessment
from storage_paths import StoragePaths


from asc_display_types import IOS_SCREENSHOT_TYPES


@dataclass
class TreatmentDefinition:
    id: str
    name: str
    app_icon_name: str | None = None
    theme: dict[str, Any] = field(default_factory=dict)
    card_overrides: dict[str, Any] = field(default_factory=dict)
    localizations: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentDefinition:
    id: str
    name: str
    traffic_proportion: int
    hypothesis: str | None = None
    platform: str | None = None
    treatments: dict[str, TreatmentDefinition] = field(default_factory=dict)


def parse_experiments(config_or_path: dict[str, Any] | Path | str) -> dict[str, ExperimentDefinition]:
    """Parse experiment definitions from a configuration dictionary or file path."""
    if isinstance(config_or_path, (str, Path)):
        path = Path(config_or_path)
        if not path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = config_or_path

    if "experiments" not in config:
        return {}

    raw_experiments = config["experiments"]
    if not isinstance(raw_experiments, dict):
        raise ValueError(f"'experiments' must be an object/dict, got {type(raw_experiments).__name__}")

    default_platform = config.get("publishing", {}).get("platform")

    valid_platforms = {"IOS", "MAC_OS", "TV_OS", "VISION_OS"}
    parsed: dict[str, ExperimentDefinition] = {}
    for exp_id, exp_data in raw_experiments.items():
        if not isinstance(exp_data, dict):
            raise ValueError(f"Experiment '{exp_id}' must be an object/dict")

        name = exp_data.get("name")
        if not name or not isinstance(name, str):
            raise ValueError(f"Experiment '{exp_id}' requires a non-empty string 'name'")

        if "trafficProportion" not in exp_data:
            raise ValueError(f"Experiment '{exp_id}' requires 'trafficProportion'")
        traffic_prop = exp_data["trafficProportion"]
        if isinstance(traffic_prop, bool) or not isinstance(traffic_prop, int) or not (1 <= traffic_prop <= 100):
            raise ValueError(
                f"Experiment '{exp_id}' trafficProportion must be an integer between 1 and 100, got {traffic_prop}"
            )

        exp_platform = exp_data.get("platform", default_platform)
        if exp_platform:
            if not isinstance(exp_platform, str) or exp_platform.upper() not in valid_platforms:
                raise ValueError(
                    f"Experiment '{exp_id}' has invalid platform '{exp_platform}'. Must be one of {sorted(valid_platforms)}"
                )
            exp_platform = exp_platform.upper()

        treatments_data = exp_data.get("treatments")
        if not isinstance(treatments_data, dict):
            raise ValueError(f"Experiment '{exp_id}' requires 'treatments' object/dict")
        if not treatments_data:
            raise ValueError(f"Experiment '{exp_id}' must define at least one treatment")

        if len(treatments_data) > 3:
            raise ValueError("An experiment supports at most three treatments")
        if "policy" in exp_data:
            if exp_platform != "IOS":
                raise ValueError("Measured screenshot experiments require platform IOS")
            assessment.preflight(config, exp_data)

        treatments: dict[str, TreatmentDefinition] = {}
        for treat_id, treat_data in treatments_data.items():
            if not isinstance(treat_data, dict):
                raise ValueError(f"Treatment '{treat_id}' in experiment '{exp_id}' must be an object/dict")
            treat_name = treat_data.get("name")
            if not treat_name or not isinstance(treat_name, str):
                raise ValueError(f"Treatment '{treat_id}' in experiment '{exp_id}' requires a non-empty string 'name'")

            if 'cardOrder' in treat_data:
                order = treat_data['cardOrder']
                ids = [card['id'] for card in config.get('cards', [])]
                if (not isinstance(order, list) or not order or any(not isinstance(v, str) for v in order)
                        or len(order) != len(ids) or len(set(order)) != len(order) or set(order) != set(ids)):
                    raise ValueError('cardOrder must be a complete permutation of unique card IDs')

            treatments[treat_id] = TreatmentDefinition(
                id=treat_id,
                name=treat_name,
                app_icon_name=treat_data.get("appIconName"),
                theme=treat_data.get("theme", {}) if isinstance(treat_data.get("theme"), dict) else {},
                card_overrides=treat_data.get("cardOverrides", {}) if isinstance(treat_data.get("cardOverrides"), dict) else {},
                localizations=treat_data.get("localizations", {}) if isinstance(treat_data.get("localizations"), dict) else {},
            )

        parsed[exp_id] = ExperimentDefinition(
            id=exp_id,
            name=name,
            traffic_proportion=int(traffic_prop),
            hypothesis=exp_data.get("hypothesis"),
            platform=exp_platform,
            treatments=treatments,
        )

    return parsed


def derive_treatment_config(
    base_config: dict[str, Any],
    experiment_id: str,
    treatment_id: str,
) -> dict[str, Any]:
    """Derive a self-contained, valid configuration for a specific experiment treatment."""
    experiments = parse_experiments(base_config)
    if experiment_id not in experiments:
        raise KeyError(f"Experiment '{experiment_id}' not found in configuration")

    exp = experiments[experiment_id]
    if treatment_id not in exp.treatments:
        raise KeyError(f"Treatment '{treatment_id}' not found in experiment '{experiment_id}'")

    treatment = exp.treatments[treatment_id]
    derived = copy.deepcopy(base_config)

    # 1. Apply theme overrides
    if treatment.theme:
        base_theme = derived.setdefault("theme", {})
        for key, val in treatment.theme.items():
            if key == "background" and isinstance(val, dict) and isinstance(base_theme.get("background"), dict):
                base_theme["background"] = {**base_theme["background"], **val}
            else:
                base_theme[key] = copy.deepcopy(val)

    # 2. Apply card overrides
    if treatment.card_overrides:
        cards = derived.setdefault("cards", [])
        for card in cards:
            cid = card.get("id")
            if cid in treatment.card_overrides:
                override = treatment.card_overrides[cid]
                for okey, oval in override.items():
                    if okey == "deviceOffset" and isinstance(oval, dict) and isinstance(card.get("deviceOffset"), dict):
                        # Partial deviceOffset patch preserves baseline keys
                        card["deviceOffset"] = {**card["deviceOffset"], **oval}
                    else:
                        card[okey] = copy.deepcopy(oval)

    order = base_config['experiments'][experiment_id]['treatments'][treatment_id].get('cardOrder')
    if order:
        cards = {card['id']: card for card in derived['cards']}
        derived['cards'] = [cards[cid] for cid in order]

    # 3. Apply localized copy overrides
    if treatment.localizations:
        locs = derived.setdefault("localizations", {})
        for locale, card_map in treatment.localizations.items():
            locale_dest = locs.setdefault(locale, {})
            for cid, card_copy in card_map.items():
                if cid in locale_dest and isinstance(locale_dest[cid], dict):
                    locale_dest[cid] = {**locale_dest[cid], **card_copy}
                else:
                    locale_dest[cid] = copy.deepcopy(card_copy)

    # 4. Storage namespace isolation for the treatment
    storage = derived.setdefault("storage", {})
    ws = storage.get("workspaceRoot", ".creative")
    obj = storage.get("objectRoot", str(Path(ws) / "objects"))
    # IDs are data, not paths; retain existing simple namespaces for compatibility.
    import re
    import hashlib
    namespace = treatment_id
    if not re.fullmatch(r"[A-Za-z0-9_-]+", namespace):
        namespace = hashlib.sha256(treatment_id.encode()).hexdigest()[:16]
    storage["workspaceRoot"] = f"{ws}-{namespace}"
    storage["objectRoot"] = f"{obj}-{namespace}"
    if exp.platform:
        derived.setdefault("publishing", {})["platform"] = exp.platform

    # 5. Metadata stamp
    derived["_experiment"] = {
        "experiment_id": experiment_id,
        "experiment_name": exp.name,
        "treatment_id": treatment_id,
        "treatment_name": treatment.name,
    }

    return derived


def validate_platform_readiness(
    platform: str,
    app_store_state: str | None = None,
    has_inflight_version: bool = False,
) -> dict[str, Any]:
    """Validate Apple App Store Connect PPO constraints for a given platform.

    Encodes Apple App Store Connect platform rules:
    - On macOS: v1 version-bound experiments are unsupported by Apple API
      ('App Store Version Platform is not supported'). v2 standalone experiments
      require app to be distributed on App Store in READY_FOR_DISTRIBUTION status
      with no pending edit drafts in PREPARE_FOR_SUBMISSION.
    - On iOS: Both v1 (version-tied in PREPARE_FOR_SUBMISSION) and v2 (standalone live)
      are supported by Apple API.
    """
    normalized_platform = platform.upper()
    if normalized_platform not in ("IOS", "MAC_OS", "TV_OS", "VISION_OS"):
        return {
            "eligible": False,
            "platform": platform,
            "endpoint": None,
            "reasons": [f"Unsupported platform: {platform}"],
        }

    if normalized_platform == "MAC_OS":
        reasons = []
        eligible = True

        if app_store_state is None:
            eligible = False
            reasons.append(
                "macOS requires app to be in READY_FOR_DISTRIBUTION / READY_FOR_SALE state on App Store Connect to create standalone v2 PPO experiments. Store state has not been verified."
            )
        elif app_store_state not in ("READY_FOR_SALE", "READY_FOR_DISTRIBUTION"):
            eligible = False
            reasons.append(
                f"App current state '{app_store_state}' is not eligible for live macOS PPO. Must be READY_FOR_DISTRIBUTION / READY_FOR_SALE."
            )

        if has_inflight_version:
            eligible = False
            reasons.append(
                "Apple App Store Connect requires macOS apps to be in READY_FOR_DISTRIBUTION without in-flight PREPARE_FOR_SUBMISSION drafts to create standalone v2 PPO experiments."
            )

        return {
            "eligible": eligible,
            "platform": "MAC_OS",
            "endpoint": "v2",
            "v1_supported": False,
            "v2_supported": True,
            "reasons": reasons if not eligible else ["macOS supports standalone v2 PPO experiments on live store versions."],
        }

    # iOS / other platforms default
    is_ios = normalized_platform == "IOS"
    return {
        "eligible": True,
        "platform": normalized_platform,
        "endpoint": "v1_or_v2" if is_ios else "v2",
        "v1_supported": is_ios,
        "v2_supported": True,
        "reasons": (
            ["iOS supports both version-bound (v1) and standalone (v2) PPO experiments."]
            if is_ios
            else [f"{normalized_platform} supports standalone v2 PPO experiments."]
        ),
    }


def reorder_only(config, treatment):
    return ('cardOrder' in treatment and not config.get('connectedTrack')
            and not any(treatment.get(key) for key in ('cardOverrides', 'localizations', 'theme')))


def compile_ppo_handoff(
    repo_root: Path,
    base_config: dict[str, Any],
    experiment_id: str,
    baseline_delivery_id: str,
    treatment_deliveries: dict[str, str],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Compile an authoritative ppo-handoff.json specification ready for ASC execution."""
    experiments = parse_experiments(base_config)
    if experiment_id not in experiments:
        raise KeyError(f"Experiment '{experiment_id}' not found in configuration")

    exp = experiments[experiment_id]
    project = base_config.get("project", {})
    publishing = base_config.get("publishing", {})
    platform = exp.platform or publishing.get("platform", "MAC_OS")
    version = publishing.get("version", "1.0")
    app_id = project.get("appStoreId") or project.get("id")

    # Read baseline delivery details
    release_root = StoragePaths.resolve(repo_root, base_config).releases
    project_slug = project.get("id", "app")
    policy = base_config['experiments'][experiment_id].get('policy')
    if policy:
        for value in (project_slug, platform, version, *treatment_deliveries.values()):
            assessment.component(value)
        if baseline_delivery_id != '<BASELINE_DELIVERY_ID>':
            assessment.component(baseline_delivery_id)
    base_del_path = release_root / project_slug / platform / version / baseline_delivery_id

    # Verify baseline delivery directory
    baseline_exists = base_del_path.is_dir()

    treatments_payload = []
    for treat_id, treat_def in exp.treatments.items():
        treat_del_id = treatment_deliveries.get(treat_id)
        treat_del_path = (
            release_root / project_slug / platform / version / treat_del_id
            if treat_del_id
            else None
        )
        treat_exists = treat_del_path.is_dir() if treat_del_path else False

        # Discover locales
        media_dir = treat_del_path / "media" if treat_del_path else None
        locales = []
        if media_dir and media_dir.is_dir():
            locales = sorted([p.name for p in media_dir.iterdir() if p.is_dir() and p.name != "preview"])

        treatments_payload.append({
            "id": treat_id,
            "definition_sha256": treatment_digest(base_config, experiment_id, treat_id),
            "name": treat_def.name,
            "delivery_id": treat_del_id,
            "delivery_exists": treat_exists,
            "app_icon_name": treat_def.app_icon_name,
            "locales": locales,
            "delivery_path": str(treat_del_path) if treat_del_path else None,
        })

    # Compile ASC command sequence plan
    asc_commands = []
    normalized_platform = platform.upper()
    v2_platforms = {"MAC_OS", "TV_OS", "VISION_OS"}
    use_v2 = normalized_platform in v2_platforms or (normalized_platform == 'IOS' and str(project.get('appStoreId', '')).isdigit())
    if use_v2:
        asc_commands.append(
            f"asc product-pages experiments create --v2 --app {shlex.quote(str(app_id))} --platform {normalized_platform} --name {shlex.quote(exp.name)} --traffic-proportion {int(exp.traffic_proportion)}"
        )
    else:
        asc_commands.append(
            f"asc product-pages experiments create --version-id '<VERSION_ID>' --name {shlex.quote(exp.name)} --traffic-proportion {int(exp.traffic_proportion)}"
        )

    for treat in treatments_payload:
        v2_flag = " --v2" if use_v2 else ""
        icon_flag = f" --app-icon-name {shlex.quote(treat['app_icon_name'])}" if treat.get("app_icon_name") else ""
        asc_commands.append(
            f"asc product-pages experiments treatments create --experiment-id '<EXPERIMENT_ID>' --name {shlex.quote(treat['name'])}{v2_flag}{icon_flag}"
        )
        locales = policy['locales'] if policy else treat['locales']
        treatment_spec = base_config['experiments'][experiment_id]['treatments'][treat['id']]
        for loc in locales:
            asc_commands.append(
                f"asc product-pages experiments treatments localizations create --treatment-id '<TREATMENT_ID>' --locale {shlex.quote(loc)}"
            )
            if policy and reorder_only(base_config, treatment_spec):
                continue  # The publisher reorders the already approved screenshots.
            directory = Path(treat['delivery_path'] or '<DELIVERY_PATH>') / 'media' / loc
            upload = "asc product-pages experiments treatments localizations screenshot-sets upload --localization-id '<LOCALIZATION_ID>'"
            if normalized_platform == 'IOS':
                targets = policy['targets'] if policy else [key for key in IOS_SCREENSHOT_TYPES if (directory / key).is_dir()]
                for target in targets:
                    asc_commands.append(f"{upload} --device-type {IOS_SCREENSHOT_TYPES[target]} --path {shlex.quote(str(directory / target))}")
            else:
                asc_commands.append(f"{upload} --path {shlex.quote(str(directory))}")

    handoff = {
        "schema_version": 1,
        "generated_by": "app-store-creative:ppo-engine",
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "bundle_id": project.get("bundleId"),
            "app_id": app_id,
            "platform": platform,
            "version": version,
        },
        "experiment": {
            "id": exp.id,
            "name": exp.name,
            "traffic_proportion": exp.traffic_proportion,
            "hypothesis": exp.hypothesis,
            "platform": platform,
        },
        "control": {
            "name": "Baseline",
            "delivery_id": baseline_delivery_id,
            "delivery_exists": baseline_exists,
            "delivery_path": str(base_del_path) if base_del_path else None,
        },
        "treatments": treatments_payload,
        "platform_readiness": validate_platform_readiness(platform),
        "asc_execution_plan": asc_commands,
    }

    spec = base_config['experiments'][experiment_id]
    if 'policy' in spec:
        handoff.update(policy=copy.deepcopy(spec['policy']), experiment_sha256=assessment.checksum(spec),
                       recipe_sha256=assessment.recipe_digest(base_config),
                       publisher_steps=["Set and verify the screenshot order in App Store Connect for each measured locale and target before binding the experiment."])
        handoff['project']['app_id'] = project.get('appStoreId')
        order = [assessment.component(card['id']) for card in base_config.get('cards', [])]
        for group in [handoff['control'], *treatments_payload]:
            treatment = spec['treatments'].get(group.get('id'), {})
            group['card_order'] = treatment.get('cardOrder', order)
            render_config = derive_treatment_config(base_config, experiment_id, group['id']) if 'id' in group else base_config
            group['composition_sha256'] = assessment.composition_digest(render_config, spec['policy'])
            group['reorder_only'] = reorder_only(base_config, treatment)
            package = Path(group['delivery_path']) if group.get('delivery_path') else None
            group['manifest_sha256'] = None
            if package and group['delivery_exists']:
                assessment.component(group['delivery_id'])
                if not package.resolve().is_relative_to(release_root):
                    raise ValueError('Invalid delivery path')
                manifest_path = package / 'manifest.json'
                if manifest_path.is_file():
                    from studio_contract import input_hashes
                    source_config = {**render_config, 'storage': base_config.get('storage', {})}
                    sources, errors = input_hashes(repo_root, source_config, policy['targets'], policy['locales'])
                    if errors:
                        raise ValueError('Cannot record measured screenshot inputs: ' + ', '.join(errors))
                    group['input_hashes'] = sources
                    group['manifest_sha256'] = assessment.digest(manifest_path)
        if output_path:
            return assessment.write_once(Path(output_path), handoff)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(handoff, f, ensure_ascii=False, indent=2)

    return handoff


def ppo_reproduce_plan(
    base_config: dict[str, Any],
    experiment_id: str,
    variant_id: str,
    decision_basis: str = "explicit --variant selection",
    measured_scope: dict | None = None,
) -> dict[str, Any]:
    """Compile a dry-run reproduction plan for the winning variant (PRD-006 R2).

    Returns a human- and agent-readable plan: provenance header, per-treatment
    derived configs (per-treatment storage namespace per R1b), and summary
    counts. No storage mutation.
    """
    experiments = parse_experiments(base_config)
    if experiment_id not in experiments:
        raise KeyError(f"Experiment '{experiment_id}' not found in configuration")
    exp = experiments[experiment_id]
    if variant_id not in exp.treatments:
        raise KeyError(
            f"Variant '{variant_id}' not found in experiment '{experiment_id}'. "
            f"Known treatments: {sorted(exp.treatments.keys())}"
        )
    derived = derive_treatment_config(base_config, experiment_id, variant_id)
    project = base_config.get("project", {})
    publishing = base_config.get("publishing", {})
    locales = derived.get("project", {}).get("locales", ["en-US"])
    targets = derived.get("targets", ["iphone_6_9"])
    if measured_scope:
        locales, targets = measured_scope['locales'], measured_scope['targets']
    plan = {
        "schema_version": 1,
        "generated_by": "app-store-creative:ppo-reproduce",
        "provenance": {
            "experiment_id": exp.id,
            "experiment_name": exp.name,
            "variant_id": variant_id,
            "variant_name": exp.treatments[variant_id].name,
            "decision_basis": decision_basis,
        },
        "project": {
            "id": project.get("id"),
            "platform": exp.platform or publishing.get("platform", "MAC_OS"),
            "version": publishing.get("version", "1.0"),
        },
        "scope": {
            "locales": locales,
            "by_locale": [{"locale": locale, "targets": list(targets)} for locale in locales],
            "targets": targets,
            "locale_count": len(locales),
            "target_count": len(targets),
            "planned_delivery_count": len(locales) * len(targets),
        },
        "treatment_config": {
            "storage_workspace": derived.get("storage", {}).get("workspaceRoot"),
            "storage_objects": derived.get("storage", {}).get("objectRoot"),
            "experiment_stamp": derived.get("_experiment"),
        },
        "dry_run": True,
    }
    return plan


def treatment_digest(config, experiment, treatment):
    from record_primitives import canonical
    return hashlib.sha256(canonical(config['experiments'][experiment]['treatments'][treatment])).hexdigest()


def selected_result(config, experiment, path):
    result = json.loads(path.read_text())
    if (result.get('generated_by') != 'app-store-creative:ppo-result'
            or result.get('project', {}).get('id') != config['project']['id']
            or result.get('experiment', {}).get('id') != experiment
            or result.get('decision') != 'use-treatment'):
        raise ValueError('Choose a result selecting a treatment for this project and experiment')
    variant = result['selected_treatment']
    if (variant not in config['experiments'][experiment]['treatments']
            or result.get('treatment_definition_sha256') != treatment_digest(config, experiment, variant)
            or result['selected_delivery'] != result['treatment_deliveries'].get(variant)):
        raise ValueError('Recorded treatment differs from the current definition or delivery')
    return variant, f"{result['market']}: {result['observation']} ({result['evidence_reference']})"


def record_result(config, handoff_path, output_path, *, market, change, observation, evidence, decision, treatment=None):
    """Record an operator's interpretation bound to the exact handoff and release IDs."""
    import os
    import tempfile

    raw = handoff_path.read_bytes()
    plan = json.loads(raw)
    if (not isinstance(plan, dict) or plan.get('generated_by') != 'app-store-creative:ppo-engine'
            or not config.get('project', {}).get('id') or plan.get('project', {}).get('id') != config['project']['id']):
        raise ValueError('Choose a PPO handoff for this project')
    control = plan['control']['delivery_id']
    variants = {row['id']: row['delivery_id'] for row in plan['treatments']}
    if not variants or not all(isinstance(value, str) and value.strip() for value in
                               [control, *variants.values(), market, change, observation, evidence]):
        raise ValueError('Provide release IDs, market, tested change, observation and evidence reference')
    if decision not in ('inconclusive', 'keep-control', 'use-treatment'):
        raise ValueError('Unknown experiment decision')
    if (decision == 'use-treatment' and treatment not in variants) or (decision != 'use-treatment' and treatment is not None):
        raise ValueError('Select a named treatment only for a use-treatment decision')
    chosen = next((row for row in plan['treatments'] if row['id'] == treatment), {})
    selected = control if decision == 'keep-control' else chosen.get('delivery_id')
    result = {'schema_version': 1, 'generated_by': 'app-store-creative:ppo-result', 'experiment': plan['experiment'], 'project': plan['project'],
              'handoff_sha256': hashlib.sha256(raw).hexdigest(), 'control_delivery': control,
              'treatment_deliveries': variants, 'market': market, 'tested_change': change,
              'observation': observation, 'evidence_reference': evidence, 'decision': decision,
              'selected_delivery': selected, 'selected_treatment': treatment,
              'treatment_definition_sha256': chosen.get('definition_sha256')}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output_path.parent) as tmp:
        json.dump(result, tmp, ensure_ascii=False, indent=2)
        tmp.write('\n')
        tmp.flush()
        os.link(tmp.name, output_path)
    return result
