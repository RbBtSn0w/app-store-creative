#!/usr/bin/env python3
"""Repository-local, dependency-free plugin packaging checks."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "app-store-creative"
MANIFEST = PLUGIN / ".codex-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
EXPECTED_PLUGIN_VERSION = "0.3.0"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(data.get("name") == PLUGIN.name, "plugin name must match its directory")
    require(data.get("version") == EXPECTED_PLUGIN_VERSION, "unexpected plugin version")
    require(data.get("author", {}).get("name") == "RbBtSn0w", "unexpected author")
    require(data.get("interface", {}).get("category") == "Creativity", "unexpected category")
    require(bool(data.get("interface", {}).get("capabilities")), "capabilities must not be empty")
    require("apps" not in data, "plugin must not declare apps")
    require("mcpServers" not in data, "plugin must not declare MCP servers")

    encoded = json.dumps(data)
    require("[" + "TO" + "DO:" not in encoded, "plugin manifest contains a placeholder")

    recipe = json.loads((PLUGIN / "assets/templates/creative.config.json").read_text())
    require(recipe.get("project", {}).get("id"), "recipe template requires a stable project ID")
    require(recipe.get("project", {}).get("locales"), "recipe template requires locales")
    require(recipe.get("targets") and recipe.get("cards"), "recipe template requires media targets and cards")
    runtime = PLUGIN / "skills/app-store-creative/runtime"
    for obsolete in ("scripts/creative_workflow.py", "scripts/asc_handoff.py",
                     "schemas/task.schema.json", "assets/templates/project.json",
                     "assets/templates/release.json"):
        require(not (runtime / obsolete).exists(), f"retired workflow payload: {obsolete}")

    marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    entries = [entry for entry in marketplace.get("plugins", []) if entry.get("name") == PLUGIN.name]
    require(len(entries) == 1, "marketplace must contain exactly one plugin entry")
    entry = entries[0]
    require(entry.get("source", {}).get("path") == "./plugins/app-store-creative", "invalid marketplace source")
    require(entry.get("category") == "Creativity", "marketplace category must be Creativity")
    require(entry.get("policy") == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }, "unexpected marketplace policy")

    runtime = PLUGIN / "skills/app-store-creative/runtime"
    for required in ("scripts/app_store_creative.py", "scripts/publication_lifecycle.py",
                         "scripts/artifact_policy.py", "scripts/media_budget.py", "scripts/relocation_object_observations.py",
                         "scripts/operation_history.py", "scripts/runtime_identity.py", "scripts/media_tool_identity.py", "scripts/asc_observation_adapter.py", "scripts/external_media_store.py", "scripts/external_delivery_archive.py",
                         "scripts/record_app_window.py", "scripts/record_app_window.swift",
                         "scripts/produce_app_preview.py",
                     "schemas/creative.config.schema.json", "assets/templates/creative.config.json",
                     "studio/dist/index.html"):
        require((runtime / required).is_file(), f"ADG skill payload missing {required}")
    canonical = json.loads((PLUGIN / ".agents/.plugin.json").read_text())
    require(canonical["version"] == EXPECTED_PLUGIN_VERSION, "stale canonical ADG version")
    require(canonical.get("selectionDependencies", {}).get("skills", {}).get("skills") ==
            ["app-store-creative"], "specialist installs must include the runtime owner")

    print(f"Validated {PLUGIN.relative_to(ROOT)} at version {EXPECTED_PLUGIN_VERSION}")


if __name__ == "__main__":
    main()
