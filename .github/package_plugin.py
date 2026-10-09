#!/usr/bin/env python3
"""Bundle the complete plugin and smoke-test its isolated runtime."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/app-store-creative"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, default=PLUGIN)
    args = parser.parse_args()
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch) / "app-store-creative"
        shutil.copytree(args.plugin_root, staged, ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", "*.pyc", ".DS_Store"))
        runtime = staged / "skills/app-store-creative/runtime"
        for required in ("scripts/app_store_creative.py", "scripts/publication_lifecycle.py",
                         "scripts/artifact_policy.py", "scripts/media_budget.py", "scripts/relocation_object_observations.py",
                         "scripts/operation_history.py", "scripts/runtime_identity.py", "scripts/media_tool_identity.py", "scripts/asc_observation_adapter.py", "scripts/external_media_store.py", "scripts/external_delivery_archive.py",
                         "scripts/record_app_window.py", "scripts/record_app_window.swift",
                         "scripts/produce_app_preview.py",
                         "schemas/creative.config.schema.json", "assets/templates/creative.config.json",
                         "studio/dist/index.html"):
            if not (runtime / required).is_file():
                raise SystemExit(f"Incomplete plugin package: missing {required}")
        subprocess.run([sys.executable, str(runtime / "scripts/app_store_creative.py"), "--help"],
                       cwd=scratch, env=environment, check=True, capture_output=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        archive = shutil.make_archive(str(Path(scratch) / "package"), "zip", scratch, staged.name)
        extracted = Path(scratch) / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        subprocess.run([sys.executable, str(extracted / staged.name / "skills/app-store-creative/runtime/scripts/app_store_creative.py"),
                        "storage", "inspect", "--repo", scratch, "--config",
                        str(extracted / staged.name / "skills/app-store-creative/runtime/assets/templates/creative.config.json")], cwd=scratch, env=environment, check=True, capture_output=True)
        for script in ("record_app_window.py", "produce_app_preview.py"):
            subprocess.run([sys.executable, str(extracted / staged.name /
                            "skills/app-store-creative/runtime/scripts" / script), "--help"],
                           cwd=scratch, env=environment, check=True, capture_output=True)
        cli = extracted / staged.name / "skills/app-store-creative/runtime/scripts/app_store_creative.py"
        probe_project = Path(scratch) / "independent-project"
        probe_project.mkdir()
        configuration = json.loads((extracted / staged.name / "skills/app-store-creative/runtime/assets/templates/creative.config.json").read_text())
        configuration["artifactPolicy"] = {"schema_version": 1, "trialRetentionDays": 3,
                                            "diagnosticRetentionDays": 2, "quarantineDays": 1,
                                            "mediaBudgetBytes": 4096}
        config_path = probe_project / "creative.config.json"
        config_path.write_text(json.dumps(configuration))
        before = {path.relative_to(probe_project).as_posix(): path.read_bytes()
                  for path in probe_project.rglob("*") if path.is_file()}
        def observe(command):
            result = subprocess.run([sys.executable, str(cli), "storage", command,
                                     "--repo", str(probe_project), "--config", str(config_path)],
                                    cwd=probe_project, env=environment, check=True,
                                    capture_output=True, text=True)
            return json.loads(result.stdout)
        policy = observe("artifact-policy")
        if policy["policy"] != configuration["artifactPolicy"] or policy["writes_performed"] is not False:
            raise SystemExit("Installed policy observation differs from configured policy")
        budget = observe("media-budget")
        if (budget["status"] != "UNKNOWN" or budget["current_payload_bytes"] is not None or
                budget["forecast_payload_bytes"] is not None or budget["configured_limit_bytes"] != 4096 or
                budget["git_history_bytes"] is not None or budget["remote_storage_bytes"] is not None or
                budget["writes_performed"] is not False):
            raise SystemExit("Installed budget observation invents uninitialized storage evidence")
        after = {path.relative_to(probe_project).as_posix(): path.read_bytes()
                 for path in probe_project.rglob("*") if path.is_file()}
        if before != after or any(path.is_dir() for path in probe_project.iterdir()):
            raise SystemExit("Installed read-only observations created project state")
        for group, command in (("publication", "retain-evidence"), ("publication", "persist-evidence"),
                               ("archive", "retrieve-evidence"),
                               ("archive", "persist-media"), ("archive", "restore-media"),
                               ("archive", "externalize"), ("archive", "restore-external"),
                               ("archive", "verify-external-git"), ("publication", "plan-external"),
                               ("publication", "prepare-external"), ("publication", "preparation-status")):
            subprocess.run([sys.executable, str(cli), group, command, "--help"],
                           cwd=scratch, env=environment, check=True, capture_output=True)
        shutil.copyfile(archive, args.output)
        print(f"Validated complete plugin package: {args.output}")


if __name__ == "__main__":
    main()
