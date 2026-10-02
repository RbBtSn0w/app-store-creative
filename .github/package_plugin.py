#!/usr/bin/env python3
"""Bundle the complete plugin and smoke-test its isolated runtime."""
import argparse
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
    with tempfile.TemporaryDirectory() as scratch:
        staged = Path(scratch) / "app-store-creative"
        shutil.copytree(args.plugin_root, staged, ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", "*.pyc", ".DS_Store"))
        for required in ("scripts/app_store_creative.py", "scripts/asc_handoff.py",
                         "schemas/creative.config.schema.json", "assets/templates/creative.config.json",
                         "studio/dist/index.html", "skills/app-store-creative/SKILL.md"):
            if not (staged / required).is_file():
                raise SystemExit(f"Incomplete plugin package: missing {required}")
        subprocess.run([sys.executable, str(staged / "scripts/app_store_creative.py"), "--help"],
                       cwd=scratch, check=True, capture_output=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        archive = shutil.make_archive(str(Path(scratch) / "package"), "zip", scratch, staged.name)
        extracted = Path(scratch) / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        subprocess.run([sys.executable, str(extracted / staged.name / "scripts/app_store_creative.py"),
                        "doctor", "--repo", scratch], cwd=scratch, check=True, capture_output=True)
        shutil.copyfile(archive, args.output)
        print(f"Validated complete plugin package: {args.output}")


if __name__ == "__main__":
    main()
