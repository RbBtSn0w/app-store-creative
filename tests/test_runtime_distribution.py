"""Run the executable payload from a skills-only installation."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins/app-store-creative"


class RuntimeDistributionTests(unittest.TestCase):
    def test_declared_skill_payload_runs_without_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "plugin"
            shutil.copytree(PLUGIN / "skills", installed / "skills",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            runtime = installed / "skills/app-store-creative/runtime"
            for name in ("scripts/app_store_creative.py", "schemas/creative.config.schema.json",
                         "assets/templates/creative.config.json", "studio/dist/index.html"):
                self.assertTrue((runtime / name).is_file(), name)
            result = subprocess.run([sys.executable, str(runtime / "scripts/app_store_creative.py"),
                                     "doctor", "--repo", directory],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
