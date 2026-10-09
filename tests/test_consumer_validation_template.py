"""The consumer validator delegates to the managed candidate contract."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime"
sys.path.insert(0, str(RUNTIME / "scripts"))
from artifact_lifecycle import Lifecycle
from test_v2_workflow import create_mock_png


class ConsumerValidationTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        config = {"project": {"id": "consumer", "locales": ["en-US"]},
                  "targets": ["mac_16_10"], "cards": [{"id": "hero", "screenshot": "source.png"}]}
        (self.root / "creative.config.json").write_text(json.dumps(config))
        self.core = Lifecycle.from_configuration(self.root)
        run = self.core.start_run({"platform": "MAC_OS", "version": "1.5"})
        attempt = self.core.start_attempt(run["id"], "render", "test-producer")
        source = self.root / "source.png"
        create_mock_png(source, 2880, 1800)
        original = self.core.register(attempt["id"], source, "source", logical_path="source.png")
        self.output = self.core.register(attempt["id"], source, "screenshot",
            inputs=[original["id"]], logical_path="en-US/mac_16_10/hero.png")
        self.core.finish_attempt(attempt["id"], "succeeded")
        self.candidate = self.core.select(run["id"], [self.output["id"]])

    def invoke(self):
        env = dict(os.environ, APP_STORE_CREATIVE_CLI=str(RUNTIME / "scripts/app_store_creative.py"),
                   APP_STORE_CREATIVE_PYTHON=sys.executable)
        return subprocess.run(["sh", str(RUNTIME / "assets/templates/validate-app-store-creative.sh"),
                               self.candidate["id"]], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def test_template_records_exact_candidate_validation(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        validation = json.loads(result.stdout)
        self.assertEqual(validation["candidate_id"], self.candidate["id"])
        self.assertEqual(validation["status"], "PASS")
        self.assertEqual(self.core._read("validations", validation["id"]), validation)
        self.assertFalse((self.root / ".creative/release-lock.json").exists())
        self.assertFalse((self.root / ".app-store-creative").exists())

    def test_template_refuses_corrupt_selected_bytes(self):
        self.core.object_path(self.output["sha256"]).write_bytes(b"changed")
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("integrity", result.stderr.lower())
        self.assertFalse((self.root / ".creative/release-lock.json").exists())
