"""Recovery explicitly locates the original workspace after configuration moves."""
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import unittest
import test_relocation_switch as fixtures


class RelocationRecoveryCLITests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def interrupted_after_config(self):
        artifact, plan = self.prepared(); original = self.store._write_path
        def fail_binding(path, data):
            if Path(path).parent.name == 'storage-bindings':
                raise OSError('Interrupted binding')
            return original(path, data)
        with patch.object(self.store, '_write_path', side_effect=fail_binding):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        return artifact, plan

    def command(self, action, plan):
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        return subprocess.run([sys.executable, str(cli), 'storage', action + '-relocate',
            '--repo', str(self.root), '--source-workspace', str(self.store.paths.workspace),
            '--id', plan['id'], '--actor', 'owner', '--reason', 'Recover interrupted switch',
            '--confirm', action.upper()], capture_output=True, text=True)

    def test_rollback_cli_uses_original_binding_after_config_changed(self):
        _, plan = self.interrupted_after_config()
        result = self.command('rollback', plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'ROLLED_BACK')
        self.assertEqual(json.loads(self.store.config_path.read_text()), self.cfg)

    def test_resume_cli_uses_original_binding_after_config_changed(self):
        _, plan = self.interrupted_after_config()
        result = self.command('resume', plan)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'SWITCHED')

    def test_authority_mismatch_rejects_recovery_without_writes(self):
        _, plan = self.interrupted_after_config()
        authority = self.store.paths.workspace / 'configuration-authority.json'
        authority.write_text(json.dumps({'config_path': str(self.root / 'other.json')}))
        before = self.store.config_path.read_bytes()
        result = self.command('rollback', plan)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.store.config_path.read_bytes(), before)
