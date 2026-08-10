#!/usr/bin/env python3
"""Repository-local, dependency-free plugin packaging checks."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "app-store-creative"
MANIFEST = PLUGIN / ".codex-plugin" / "plugin.json"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
EXPECTED_VERSION = "0.1.0"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(data.get("name") == PLUGIN.name, "plugin name must match its directory")
    require(data.get("version") == EXPECTED_VERSION, "unexpected plugin version")
    require(data.get("author", {}).get("name") == "RbBtSn0w", "unexpected author")
    require(data.get("interface", {}).get("category") == "Creativity", "unexpected category")
    require(bool(data.get("interface", {}).get("capabilities")), "capabilities must not be empty")
    require("apps" not in data, "plugin must not declare apps")
    require("mcpServers" not in data, "plugin must not declare MCP servers")

    encoded = json.dumps(data)
    require("[" + "TO" + "DO:" not in encoded, "plugin manifest contains a placeholder")

    templates = {}
    for template_name in ("project.json", "release.json"):
        template = json.loads(
            (PLUGIN / "assets" / "templates" / template_name).read_text(encoding="utf-8")
        )
        require(template.get("plugin_version") == EXPECTED_VERSION, f"stale {template_name}")
        templates[template_name] = template

    project = templates["project.json"]
    require(project.get("product", {}).get("bundle_id"), "project template requires a bundle ID")
    require(project.get("product", {}).get("platforms"), "project template requires platforms")
    require(project.get("dependencies", {}).get("figma", {}).get("plugin") == "figma", "missing Figma dependency")
    require(project.get("capture", {}).get("adapter"), "project template requires a capture adapter")
    require(project.get("paths", {}).get("release_manifest"), "project template requires release paths")

    release = templates["release.json"]
    require(release.get("targets"), "release template requires targets")
    require(release.get("locales") and release.get("scenes"), "release template requires locales and scenes")
    require(release.get("preview", {}).get("codec"), "release template requires a preview contract")
    require(release.get("approval_policy", {}).get("upload") == "required", "upload approval must be required")
    require(release.get("approval_policy", {}).get("confirmation_tokens") == {
        "approve": "APPROVE",
        "promote": "PROMOTE",
        "upload": "UPLOAD",
    }, "release template confirmation tokens must match the stable CLI")
    require(release.get("publishing") == {
        "engine_upload_mode": "dry-run",
        "mutation_executor": "official-asc-plugin",
    }, "v0.1 publishing contract must preserve the ASC boundary")
    require(release.get("remoteWrite") is False, "remoteWrite must default to false")

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

    print(f"Validated {PLUGIN.relative_to(ROOT)} at version {EXPECTED_VERSION}")


if __name__ == "__main__":
    main()
