"""Recovery status remains readable without mutating fenced storage."""
import unittest
from unittest.mock import patch
import test_relocation_switch as fixtures


class RelocationStatusTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def records(self):
        return {str(p.relative_to(self.store.paths.workspace)): p.read_bytes()
                for p in self.store.paths.workspace.rglob('*.json')}

    def test_copied_object_check_is_independent_of_activation(self):
        from pathlib import Path
        artifact, plan = self.prepared()
        self.assertEqual(self.store.relocated_object_status(plan['id'])['status'], 'INCOMPLETE')
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        self.assertEqual(self.store.relocated_object_status(plan['id'])['status'], 'UNKNOWN')
        from artifact_lifecycle import Lifecycle
        import json
        target = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        target.start_run({})
        before = self.records()
        result = self.store.relocated_object_status(plan['id'])
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['object_integrity_verified'])
        self.assertEqual(self.records(), before)
        entry = next(item for item in plan['files'] if item['root'] == 'objects')
        (Path(plan['to']['objects']) / entry['path']).write_bytes(b'Changed object')
        self.assertEqual(self.store.relocation_status(plan['id'])['target_activation_status'], 'VERIFIED')
        self.assertEqual(self.store.relocated_object_status(plan['id'])['status'], 'FAIL')
        self.assertEqual(self.records(), before)

    def test_copied_object_inspection_rejects_changed_source_or_target_plan(self):
        import json
        from artifact_lifecycle import Lifecycle
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'fixture-owner', 'Disposable fixture')
        target = Lifecycle.from_configuration(self.root, self.store.config_path)
        target.start_run({})
        for path in (self.store._path('relocations', plan['id']), target._path('relocations', plan['id'])):
            with self.subTest(path=path):
                before = path.read_bytes()
                changed = json.loads(before)
                item = next(item for item in changed['files'] if item['root'] == 'objects')
                item['sha256'] = '0' * 64
                path.write_text(json.dumps(changed))
                result = self.store.relocated_object_status(plan['id'])
                self.assertEqual(result['status'], 'FAIL', result)
                self.assertFalse(result['object_integrity_verified'])
                self.assertEqual(json.loads(path.read_text()), changed)
                path.write_bytes(before)
        self.assertEqual(self.store.relocated_object_status(plan['id'])['status'], 'PASS')

    def test_prepared_status_is_read_only(self):
        artifact, plan = self.prepared()
        before = self.records()
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['status'], 'PREPARED')
        self.assertTrue(result['current_binding_writable'])
        self.assertFalse(result['source_deleted'])
        self.assertEqual(self.records(), before)

    def test_switched_source_is_fenced_and_requires_reverse_migration(self):
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        before = self.records()
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['status'], 'SWITCHED')
        self.assertFalse(result['current_binding_writable'])
        self.assertEqual(result['recovery'], 'REVERSE_RELOCATION_REQUIRED')
        self.assertEqual(self.records(), before)

    def test_interrupted_switch_requires_explicit_recovery(self):
        artifact, plan = self.prepared()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Configuration failed')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Move')
        before = self.records()
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['status'], 'SWITCH_INTERRUPTED')
        self.assertFalse(result['current_binding_writable'])
        self.assertEqual(result['recovery'], 'RESUME_OR_ROLLBACK')
        self.assertEqual(self.records(), before)

    def test_invalid_switched_receipt_cannot_report_switched(self):
        import json
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        path = self.store._path('relocations', plan['id'], 'switched')
        receipt = json.loads(path.read_text())
        receipt['status'] = 'FAILED'
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'receipt status'):
            self.store.relocation_status(plan['id'])

    def test_cli_reads_prepared_status(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        artifact, plan = self.prepared()
        script = Path(__file__).resolve().parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'storage', 'status-relocate',
                                 '--repo', str(self.root), '--id', plan['id']],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.store.relocation_status(plan['id']))

    def test_source_status_rechecks_target_activation_without_writes(self):
        import json
        from pathlib import Path
        from artifact_lifecycle import canonical
        import hashlib
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        before = self.records()
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['target_activation_status'], 'VERIFIED')
        self.assertEqual(self.records(), before)
        key = hashlib.sha256(canonical(plan['to'])).hexdigest()
        path = Path(plan['to']['workspace']) / 'records/storage-activations' / (key + '.json')
        data = json.loads(path.read_text())
        data['switch_sha256'] = '0' * 64
        path.write_text(json.dumps(data))
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['status'], 'SWITCHED')
        self.assertEqual(result['target_activation_status'], 'FAIL')
        self.assertTrue(result['target_activation_errors'])
        self.assertFalse(result['media_integrity_verified'])

    def test_missing_target_does_not_get_recreated_by_status(self):
        from pathlib import Path
        import shutil
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        target = Path(plan['to']['workspace'])
        shutil.rmtree(target)
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['target_activation_status'], 'FAIL')
        self.assertFalse(target.exists())

    def test_target_activation_requires_intent_bound_plan_and_receipt(self):
        import json
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        path = self.store._path('relocations', plan['id'])
        original = path.read_bytes()
        changed = json.loads(original); changed['files'][0]['sha256'] = '0' * 64
        path.write_text(json.dumps(changed))
        before = self.records()
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['target_activation_status'], 'FAIL')
        self.assertEqual(self.records(), before)
        path.write_bytes(original)
        intent_path = self.store._path('relocations', plan['id'], 'switch-intent')
        intent = json.loads(intent_path.read_text()); intent['receipt']['actor'] = 'different-owner'
        intent_path.write_text(json.dumps(intent))
        before = self.records()
        result = self.store.relocation_status(plan['id'])
        self.assertEqual(result['target_activation_status'], 'FAIL')
        self.assertEqual(self.records(), before)

    def test_missing_source_fence_never_reenables_writes_after_switch(self):
        import hashlib
        from artifact_lifecycle import canonical
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        key = hashlib.sha256(canonical(plan['from'])).hexdigest()
        self.store._path('storage-fences', key, plan['id']).unlink()
        before = self.records()
        status = self.store.relocation_status(plan['id'])
        self.assertFalse(status['current_binding_writable'])
        self.assertTrue(status['errors'])
        with self.assertRaisesRegex(ValueError, 'fence'):
            self.store.start_run({})
        self.assertEqual(self.records(), before)

    def test_target_activation_rechecks_control_journal_and_published_binding(self):
        import json
        from pathlib import Path
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        intent_path = self.store._path('relocations', plan['id'], 'switch-intent')
        original = intent_path.read_bytes()
        intent = json.loads(original)
        intent['storage_controls']['storage-bindings']['after']['switch_sha256'] = '0' * 64
        intent_path.write_text(json.dumps(intent))
        before = self.records()
        self.assertEqual(self.store.relocation_status(plan['id'])['target_activation_status'], 'FAIL')
        self.assertEqual(self.records(), before)
        intent_path.write_bytes(original)
        intent = json.loads(original)
        key = intent['storage_controls']['storage-bindings']['key']
        path = Path(plan['to']['workspace']) / 'records/storage-bindings' / (key + '.json')
        binding = json.loads(path.read_text()); binding['switch_sha256'] = '0' * 64
        path.write_text(json.dumps(binding))
        before = path.read_bytes()
        self.assertEqual(self.store.relocation_status(plan['id'])['target_activation_status'], 'FAIL')
        self.assertEqual(path.read_bytes(), before)
