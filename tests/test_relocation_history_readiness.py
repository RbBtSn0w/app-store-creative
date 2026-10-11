"""Activated relocation roots support history reads before any new mutation."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class RelocationHistoryReadinessTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def inspect(self, core):
        records = core.paths.workspace / 'records'
        before = {str(path): path.read_bytes() for path in records.rglob('*.json')}
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'history', 'verify',
            '--repo', str(self.root)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'PASS')
        self.assertEqual(before, {str(path): path.read_bytes() for path in records.rglob('*.json')})

    def test_forward_activation_supports_first_history_read(self):
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'fixture-owner', 'Move fixture')
        self.inspect(Lifecycle.from_configuration(self.root, self.store.config_path))

    def test_reverse_activation_supports_first_history_read(self):
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'fixture-owner', 'Move fixture')
        moved = Lifecycle.from_configuration(self.root, self.store.config_path)
        reverse = moved.plan_reverse_relocation(plan['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'fixture-owner', 'Return fixture')
        moved.switch_reverse_relocation(reverse['id'], 'fixture-owner', 'Return fixture')
        self.inspect(Lifecycle.from_configuration(self.root, self.store.config_path))

    def test_cancel_preserves_modified_prepared_lock(self):
        _, plan = self.prepared()
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        lock = Path(self.store._prepared_relocation_lock(plan, prepared)['path'])
        lock.write_bytes(b'Preserve unexpected owner bytes')
        result = self.store.cancel_relocation(plan['id'], 'fixture-owner', 'Cancel safely')
        self.assertEqual(result['status'], 'CANCELLED_PARTIAL')
        self.assertEqual(lock.read_bytes(), b'Preserve unexpected owner bytes')
