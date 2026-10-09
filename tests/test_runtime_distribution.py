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
            for name in ("scripts/app_store_creative.py", "scripts/operation_history.py", "schemas/creative.config.schema.json",
                         "assets/templates/creative.config.json", "studio/dist/index.html"):
                self.assertTrue((runtime / name).is_file(), name)
            for obsolete in ("scripts/creative_workflow.py", "scripts/asc_handoff.py",
                             "schemas/task.schema.json", "assets/templates/project.json",
                             "assets/templates/release.json"):
                self.assertFalse((runtime / obsolete).exists(), obsolete)
            result = subprocess.run([sys.executable, str(runtime / "scripts/app_store_creative.py"),
                                     "storage", "inspect", "--repo", directory, "--config",
                                     str(runtime / "assets/templates/creative.config.json")],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_installed_shell_entrypoint_uses_managed_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "plugin"
            shutil.copytree(PLUGIN / "skills", installed / "skills",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            runtime = installed / "skills/app-store-creative/runtime"
            result = subprocess.run(["sh", str(runtime / "scripts/app-store-creative"),
                                     "storage", "inspect", "--repo", directory, "--config",
                                     str(runtime / "assets/templates/creative.config.json")],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((Path(directory) / ".app-store-creative").exists())

    def test_new_project_template_requires_reviewed_localized_inputs(self):
        import json
        config = json.loads((PLUGIN / 'assets/templates/creative.config.json').read_text())
        self.assertIs(config.get('studio', {}).get('requireExportEvidence'), True)
        default = config['project']['defaultLocale']
        for locale in config['project']['locales']:
            if locale == default:
                continue
            for card in config['cards']:
                localized = config['localizations'][locale][card['id']]
                self.assertIn('screenshot', localized)
                self.assertNotEqual(localized['screenshot'], card['screenshot'])
