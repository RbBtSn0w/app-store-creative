"""Apply review directives directly to creative.config.json without requiring an active web server."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
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

    # 1. Parse directives input (supporting direct JSON string, file path, or stdin via '-')
    if directives_json is not None:
        if directives_json.strip() == "-":
            raw_str = sys.stdin.read()
        else:
            raw_str = directives_json
        try:
            raw = json.loads(raw_str)
        except Exception as e:
            raise ValueError(f"Invalid JSON in directives string: {e}") from e
    else:
        if directives_file and str(directives_file).strip() == "-":
            raw_str = sys.stdin.read()
            try:
                raw = json.loads(raw_str)
            except Exception as e:
                raise ValueError(f"Invalid JSON from stdin: {e}") from e
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
    initial_bytes = cfg_file.read_bytes()
    config = json.loads(initial_bytes.decode("utf-8"))

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
        patch = item.get("patch")
        if not isinstance(patch, dict):
            continue

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

            valid_keys = {"rotateX", "rotateY", "rotate", "scale", "x", "y"}
            supplied_offset = {
                k: float(v) for k, v in offset.items() if k in valid_keys
            }

            if target:
                matching_card.setdefault("variants", {}).setdefault(target, {})
                matching_card["variants"][target].setdefault("deviceOffset", {})
                matching_card["variants"][target]["deviceOffset"].update(supplied_offset)
            else:
                matching_card.setdefault("deviceOffset", {})
                matching_card["deviceOffset"].update(supplied_offset)

        # 4b. Update Headline (with variant localization precedence)
        if "headline" in patch and isinstance(patch["headline"], str):
            h = patch["headline"]
            if locale == default_locale:
                if target:
                    matching_card.setdefault("variants", {}).setdefault(target, {})
                    matching_card["variants"][target]["headline"] = h
                else:
                    matching_card["headline"] = h
            else:
                if target:
                    matching_card.setdefault("variants", {}).setdefault(target, {}).setdefault("localizations", {}).setdefault(locale, {})
                    matching_card["variants"][target]["localizations"][locale]["headline"] = h
                else:
                    config.setdefault("localizations", {}).setdefault(locale, {}).setdefault(card_id, {})
                    config["localizations"][locale][card_id]["headline"] = h

        # 4c. Update Subheadline (with variant localization precedence)
        if "subheadline" in patch and isinstance(patch["subheadline"], str):
            sh = patch["subheadline"]
            if locale == default_locale:
                if target:
                    matching_card.setdefault("variants", {}).setdefault(target, {})
                    matching_card["variants"][target]["subheadline"] = sh
                else:
                    matching_card["subheadline"] = sh
            else:
                if target:
                    matching_card.setdefault("variants", {}).setdefault(target, {}).setdefault("localizations", {}).setdefault(locale, {})
                    matching_card["variants"][target]["localizations"][locale]["subheadline"] = sh
                else:
                    config.setdefault("localizations", {}).setdefault(locale, {}).setdefault(card_id, {})
                    config["localizations"][locale][card_id]["subheadline"] = sh

        # 4d. Update Layout
        if "layout" in patch and isinstance(patch["layout"], str):
            if target:
                matching_card.setdefault("variants", {}).setdefault(target, {})
                matching_card["variants"][target]["layout"] = patch["layout"]
            else:
                matching_card["layout"] = patch["layout"]

        if card_id not in updated_card_ids:
            updated_card_ids.append(card_id)

    # 5. Validate resulting configuration
    studio_contract.check_config(config)

    directives_sync_warning = None

    # 6. Atomically persist changes
    with studio_contract.WRITE_LOCK:
        current_bytes = cfg_file.read_bytes() if cfg_file.exists() else b""
        if studio_contract.digest(current_bytes) != studio_contract.digest(initial_bytes):
            raise ValueError("Configuration changed concurrently on disk; aborting apply-critique to prevent lost updates")
        studio_contract.atomic_json(cfg_file, config)

        # 6b. Keep .creative/review-directives.json synchronized
        try:
            directives_path = repo / ".creative" / "review-directives.json"
            directives_path.parent.mkdir(parents=True, exist_ok=True)
            existing_data = {}
            if directives_path.is_file():
                try:
                    existing_data = json.loads(directives_path.read_text(encoding="utf-8"))
                except Exception as e:
                    raise ValueError(f"Failed to read existing review-directives.json: {e}")
            if not isinstance(existing_data, dict):
                raise ValueError("Existing review-directives.json must be a JSON object")
            persisted_directives = existing_data.get("directives", {})
            if not isinstance(persisted_directives, dict):
                persisted_directives = {}
            for item in directive_list:
                cid = item.get("card_id") or item.get("cardId")
                if cid and isinstance(cid, str):
                    persisted_directives[cid.strip()] = item
                    existing_data["latest"] = item
            existing_data["directives"] = persisted_directives
            studio_contract.atomic_json(directives_path, existing_data)
        except Exception as e:
            directives_sync_warning = str(e)

    res = {
        "status": "ok",
        "updated_cards": updated_card_ids,
        "config_path": str(cfg_file),
        "directives_applied": len(updated_card_ids),
    }
    if directives_sync_warning:
        res["directives_sync_warning"] = directives_sync_warning
    return res
