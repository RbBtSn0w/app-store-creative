"""Apply review directives directly to creative.config.json without requiring an active web server."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import studio_contract


def apply_critique(
    repo_root: Path,
    config_path: Path | None = None,
    directives_file: Path | None = None,
    directives_json: str | None = None,
) -> dict[str, Any]:
    """Parse review directives and atomically merge them into creative.config.json."""
    repo = Path(repo_root).resolve()
    cfg_file = (config_path if config_path and Path(config_path).is_absolute() else repo / (config_path or "creative.config.json")).resolve()
    if not cfg_file.is_file():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    # 1. Parse directives input
    if directives_json is not None:
        try:
            raw = json.loads(directives_json)
        except Exception as e:
            raise ValueError(f"Invalid JSON in directives string: {e}") from e
    else:
        d_file = (directives_file if directives_file and Path(directives_file).is_absolute() else repo / (directives_file or ".creative/review-directives.json")).resolve()
        if not d_file.is_file():
            raise FileNotFoundError(f"Review directives file not found: {d_file}")
        with open(d_file, "r", encoding="utf-8") as f:
            raw = json.load(f)

    # 2. Normalize directive list
    directive_list: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        if isinstance(raw.get("directives"), dict):
            directive_list = [v for v in raw["directives"].values() if isinstance(v, dict)]
        elif isinstance(raw.get("latest"), dict) and not raw.get("directives"):
            directive_list = [raw["latest"]]
        elif raw.get("card_id") or raw.get("cardId"):
            directive_list = [raw]
        else:
            raise ValueError("No valid directives found in payload")
    elif isinstance(raw, list):
        directive_list = [item for item in raw if isinstance(item, dict)]
    else:
        raise ValueError("Directives payload must be a JSON object or array")

    if not directive_list:
        return {
            "status": "ok",
            "message": "No directives to apply",
            "updated_cards": [],
            "config_path": str(cfg_file),
            "directives_applied": 0,
        }

    # 3. Load & validate existing config
    with open(cfg_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    studio_contract.check_config(config)
    default_locale = config.get("project", {}).get("defaultLocale", "en-US")

    # 4. Apply each directive
    updated_card_ids: list[str] = []
    for item in directive_list:
        card_id = item.get("card_id") or item.get("cardId")
        if not card_id or not isinstance(card_id, str):
            continue
        card_id = card_id.strip()

        target = item.get("target")
        locale = item.get("locale") or default_locale
        patch = item.get("patch") if isinstance(item.get("patch"), dict) else item

        matching_card = next((c for c in config.get("cards", []) if c.get("id") == card_id), None)
        if not matching_card:
            raise ValueError(f"Card '{card_id}' not found in configuration")

        # 4a. Update 3D deviceOffset
        if "deviceOffset" in patch:
            offset = patch["deviceOffset"]
            if not isinstance(offset, dict) or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in offset.values()
            ):
                raise ValueError(f"Card '{card_id}' deviceOffset requires finite numeric values")

            normalized_offset = {
                "rotateX": float(offset.get("rotateX", 0)),
                "rotateY": float(offset.get("rotateY", 0)),
                "rotate": float(offset.get("rotate", 0)),
                "scale": float(offset.get("scale", 1.0)),
                "x": float(offset.get("x", 0)),
                "y": float(offset.get("y", 0)),
            }

            if target and "variants" in matching_card and target in matching_card["variants"]:
                matching_card["variants"][target].setdefault("deviceOffset", {})
                matching_card["variants"][target]["deviceOffset"].update(normalized_offset)
            else:
                matching_card.setdefault("deviceOffset", {})
                matching_card["deviceOffset"].update(normalized_offset)

        # 4b. Update Headline
        if "headline" in patch and isinstance(patch["headline"], str):
            h = patch["headline"]
            if locale == default_locale:
                if target and "variants" in matching_card and target in matching_card["variants"]:
                    matching_card["variants"][target]["headline"] = h
                else:
                    matching_card["headline"] = h
            else:
                config.setdefault("localizations", {}).setdefault(locale, {}).setdefault(card_id, {})
                config["localizations"][locale][card_id]["headline"] = h

        # 4c. Update Subheadline
        if "subheadline" in patch and isinstance(patch["subheadline"], str):
            sh = patch["subheadline"]
            if locale == default_locale:
                if target and "variants" in matching_card and target in matching_card["variants"]:
                    matching_card["variants"][target]["subheadline"] = sh
                else:
                    matching_card["subheadline"] = sh
            else:
                config.setdefault("localizations", {}).setdefault(locale, {}).setdefault(card_id, {})
                config["localizations"][locale][card_id]["subheadline"] = sh

        # 4d. Update Layout
        if "layout" in patch and isinstance(patch["layout"], str):
            if target and "variants" in matching_card and target in matching_card["variants"]:
                matching_card["variants"][target]["layout"] = patch["layout"]
            else:
                matching_card["layout"] = patch["layout"]

        if card_id not in updated_card_ids:
            updated_card_ids.append(card_id)

    # 5. Validate resulting configuration
    studio_contract.check_config(config)

    # 6. Atomically persist changes
    with studio_contract.WRITE_LOCK:
        studio_contract.atomic_json(cfg_file, config)

    return {
        "status": "ok",
        "updated_cards": updated_card_ids,
        "config_path": str(cfg_file),
        "directives_applied": len(updated_card_ids),
    }
