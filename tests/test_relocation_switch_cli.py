"""The public relocation workflow uses the verified lifecycle kernel."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class RelocationSwitchCLITests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets

    def cli(self, *arguments):
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'storage', *arguments,
                                 '--repo', str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_plan_prepare_switch_and_new_writes(self):
        artifact = self.source(); self.store.config_path.write_text(json.dumps(self.cfg))
        (self.root / 'target-storage.json').write_text(json.dumps(self.targets()))
        plan = self.cli('plan-relocate', '--storage', 'target-storage.json')
        self.cli('prepare-relocate', '--id', plan['id'], '--actor', 'owner',
                 '--reason', 'Prepare approved location', '--confirm', 'PREPARE')
        receipt = self.cli('switch-relocate', '--id', plan['id'], '--actor', 'owner',
                           '--reason', 'Switch verified location', '--confirm', 'SWITCH')
        self.assertEqual(receipt['status'], 'SWITCHED')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        moved.verify_artifact(artifact['id']); moved.start_run({})
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.start_run({})
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())
