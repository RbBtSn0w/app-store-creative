#!/bin/sh
set -eu

EXPECTED_PLUGIN_VERSION="0.1.0"

usage() {
  echo "Usage: $0 [project.json] [release.json]" >&2
  echo "Set APP_STORE_CREATIVE_CLI to a local app_store_creative.py runtime." >&2
}

PROJECT_MANIFEST="${1:-project.json}"
RELEASE_MANIFEST="${2:-release.json}"
CLI="${APP_STORE_CREATIVE_CLI:-.app-store-creative/runtime/${EXPECTED_PLUGIN_VERSION}/app_store_creative.py}"

if [ "$#" -gt 2 ]; then
  usage
  exit 64
fi

for path in "$PROJECT_MANIFEST" "$RELEASE_MANIFEST" "$CLI"; do
  if [ ! -f "$path" ]; then
    echo "Missing required local file: $path" >&2
    exit 66
  fi
done

export APP_STORE_CREATIVE_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1

MANIFEST_DATA="$(python3 - "$EXPECTED_PLUGIN_VERSION" "$PROJECT_MANIFEST" "$RELEASE_MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

expected_version, project_path, release_path = sys.argv[1:]

def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Invalid JSON manifest {path}: {error}")

project = load(project_path)
release = load(release_path)

for label, document in (("project", project), ("release", release)):
    if document.get("schema_version") != 1:
        raise SystemExit(f"Unsupported {label} schema_version: {document.get('schema_version')!r}")
    if document.get("plugin_version") != expected_version:
        raise SystemExit(
            f"{label} plugin_version must be {expected_version}, "
            f"got {document.get('plugin_version')!r}"
        )

project_id = project.get("project", {}).get("id")
if not isinstance(project_id, str) or not project_id:
    raise SystemExit("project.project.id must be a non-empty string")
if release.get("project_id") != project_id:
    raise SystemExit("release.project_id must match project.project.id")

product = project.get("product", {})
for field in ("name", "bundle_id", "default_locale"):
    if not isinstance(product.get(field), str) or not product[field]:
        raise SystemExit(f"project.product.{field} must be a non-empty string")
if not isinstance(product.get("platforms"), list) or not product["platforms"]:
    raise SystemExit("project.product.platforms must be a non-empty array")

dependencies = project.get("dependencies", {})
if dependencies.get("figma", {}).get("plugin") != "figma":
    raise SystemExit("project.dependencies.figma.plugin must be figma")
if dependencies.get("app_store_connect", {}).get("plugin") != "asc":
    raise SystemExit("project.dependencies.app_store_connect.plugin must be asc")
if not isinstance(project.get("capture", {}).get("adapter"), str):
    raise SystemExit("project.capture.adapter must be a string")
for field in ("release_manifest", "artifacts", "runtime"):
    if not isinstance(project.get("paths", {}).get(field), str):
        raise SystemExit(f"project.paths.{field} must be a string")

targets = release.get("targets")
if not isinstance(targets, list) or not targets:
    raise SystemExit("release.targets must be a non-empty array")
for target in targets:
    for field in ("display_type", "device_type"):
        if not isinstance(target.get(field), str) or not target[field]:
            raise SystemExit(f"every release target requires {field}")
    dimensions = target.get("dimensions")
    if not (
        isinstance(dimensions, list)
        and len(dimensions) == 2
        and all(isinstance(value, int) and value > 0 for value in dimensions)
    ):
        raise SystemExit("every release target requires positive width and height")

for field in ("locales", "scenes"):
    if not isinstance(release.get(field), list) or not release[field]:
        raise SystemExit(f"release.{field} must be a non-empty array")

preview = release.get("preview", {})
for field in ("orientation", "dimensions", "fps", "duration_seconds", "codec", "audio"):
    if field not in preview:
        raise SystemExit(f"release.preview.{field} is required")
if release.get("approval_policy", {}).get("design") != "required":
    raise SystemExit("release.approval_policy.design must be required")
if release.get("approval_policy", {}).get("upload") != "required":
    raise SystemExit("release.approval_policy.upload must be required")
tokens = release.get("approval_policy", {}).get("confirmation_tokens", {})
expected_tokens = {"approve": "APPROVE", "promote": "PROMOTE", "upload": "UPLOAD"}
if tokens != expected_tokens:
    raise SystemExit("release approval confirmation tokens do not match the stable CLI")
publishing = release.get("publishing", {})
if publishing.get("engine_upload_mode") != "dry-run":
    raise SystemExit("release.publishing.engine_upload_mode must be dry-run for v0.1")
if publishing.get("mutation_executor") != "official-asc-plugin":
    raise SystemExit("release publishing mutation executor must be the official ASC plugin")
if release.get("remoteWrite") is not False:
    raise SystemExit("release.remoteWrite must default to false")

print(project_id)
PY
)"

VALIDATION_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/app-store-creative.XXXXXX")"
cleanup() {
  rm -rf "$VALIDATION_ROOT"
}
trap cleanup EXIT HUP INT TERM

python3 "$CLI" doctor --repo "$VALIDATION_ROOT" --json >/dev/null
python3 "$CLI" init --repo "$VALIDATION_ROOT" >/dev/null
python3 "$CLI" plan --repo "$VALIDATION_ROOT" --release "$RELEASE_MANIFEST" >/dev/null
python3 "$CLI" audit \
  --repo "$VALIDATION_ROOT" \
  --release "$RELEASE_MANIFEST" \
  --app "$MANIFEST_DATA" \
  --version-id "template-validation"
