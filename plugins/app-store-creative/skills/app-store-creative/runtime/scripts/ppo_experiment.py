#!/usr/bin/env python3
"""Product Page Optimization (PPO) experiment engine and ASC handoff compiler.

Provides declarative experiment definitions, treatment configuration derivation,
platform readiness validation, and authoritative ASC PPO handoff manifest generation.
"""

from __future__ import annotations

import copy
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from artifact_lifecycle import StoragePaths


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

        treatments: dict[str, TreatmentDefinition] = {}
        for treat_id, treat_data in treatments_data.items():
            if not isinstance(treat_data, dict):
                raise ValueError(f"Treatment '{treat_id}' in experiment '{exp_id}' must be an object/dict")
            treat_name = treat_data.get("name")
            if not treat_name or not isinstance(treat_name, str):
                raise ValueError(f"Treatment '{treat_id}' in experiment '{exp_id}' requires a non-empty string 'name'")

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
    if normalized_platform in v2_platforms:
        asc_commands.append(
            f"asc product-pages experiments create --v2 --app {shlex.quote(str(app_id))} --platform {normalized_platform} --name {shlex.quote(exp.name)} --traffic-proportion {int(exp.traffic_proportion)}"
        )
    else:
        asc_commands.append(
            f"asc product-pages experiments create --name {shlex.quote(exp.name)} --traffic-proportion {int(exp.traffic_proportion)}"
        )

    for treat in treatments_payload:
        v2_flag = " --v2" if normalized_platform in v2_platforms else ""
        icon_flag = f" --app-icon-name {shlex.quote(treat['app_icon_name'])}" if treat.get("app_icon_name") else ""
        asc_commands.append(
            f"asc product-pages experiments treatments create --experiment-id '<EXPERIMENT_ID>' --name {shlex.quote(treat['name'])}{v2_flag}{icon_flag}"
        )
        for loc in treat["locales"]:
            asc_commands.append(
                f"asc product-pages experiments treatments localizations create --treatment-id '<TREATMENT_ID>' --locale {shlex.quote(loc)}"
            )
            # Screenshot set upload
            loc_path = f"{treat['delivery_path']}/media/{loc}" if treat.get("delivery_path") else f"<DELIVERY_PATH>/media/{loc}"
            asc_commands.append(
                f"asc product-pages experiments treatments localizations screenshot-sets upload --localization-id '<LOCALIZATION_ID>' --path {shlex.quote(loc_path)}"
            )

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
