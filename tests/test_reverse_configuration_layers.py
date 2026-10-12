"""Reverse relocation revalidates both configuration layers before exchanging roots."""
import base64
import json
from pathlib import Path
import unittest
import test_reverse_relocation_switch as fixtures


class ReverseConfigurationLayersTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationSwitchTests.setUp
    source = fixtures.ReverseRelocationSwitchTests.source
    targets = fixtures.ReverseRelocationSwitchTests.targets
    prepared = fixtures.ReverseRelocationSwitchTests.prepared
    moved = fixtures.ReverseRelocationSwitchTests.moved
    reverse = fixtures.ReverseRelocationSwitchTests.reverse

    def local(self, moved):
        from configuration_layers import local_path_for
        path = local_path_for(moved.config_path)
        path.write_text(json.dumps({'schema_version':1, 'project_id':self.cfg['project']['id'], 'storage':{}}))
        return path

    def test_reverse_plan_pins_current_source_and_original_target(self):
        artifact, forward, moved = self.moved()
        plan = moved.plan_reverse_relocation(forward['id'])
        change = plan['configuration_change']
        self.assertEqual(base64.b64decode(change['source_project_bytes_base64']), moved.config_path.read_bytes())
        self.assertEqual(change['source_binding'], forward['to'])
        self.assertEqual(change['target_binding'], forward['from'])
        self.assertIsNone(change['source_local_sha256'])
        self.assertEqual(moved.verify_reverse_relocation_plan(plan['id'])['status'], 'READY')

    def test_local_appearance_invalidates_return_plan(self):
        artifact, forward, moved = self.moved()
        plan = moved.plan_reverse_relocation(forward['id']); local = self.local(moved)
        with self.assertRaisesRegex(ValueError, 'layer|stale|differs'):
            moved.verify_reverse_relocation_plan(plan['id'])
        moved.verify_artifact(artifact['id']); self.assertTrue(local.exists())

    def test_return_preparation_refuses_new_local_file_before_copy(self):
        artifact, forward, moved = self.moved()
        plan = moved.plan_reverse_relocation(forward['id']); self.local(moved)
        before = {str(path):path.read_bytes() for path in (moved.paths.workspace / 'records').rglob('*.json')}
        with self.assertRaisesRegex(ValueError, 'layer|stale|differs'):
            moved.prepare_reverse_relocation(plan['id'], 'owner', 'Return')
        self.assertEqual({str(path):path.read_bytes() for path in (moved.paths.workspace / 'records').rglob('*.json')}, before)

    def test_same_byte_configuration_replacement_refuses_root_exchange(self):
        artifact, forward, moved, plan, run = self.reverse()
        paths = [Path(value) for value in {*forward['from'].values(), *forward['to'].values()} if Path(value).exists()]
        identities = {str(path):(path.stat().st_dev,path.stat().st_ino) for path in paths}
        replaced = moved.config_path.with_name('replacement.json'); replaced.write_bytes(moved.config_path.read_bytes()); replaced.replace(moved.config_path)
        with self.assertRaisesRegex(ValueError, 'layer|stale|differs'):
            moved.switch_reverse_relocation(plan['id'], 'owner', 'Return')
        self.assertFalse(moved._path('relocations', plan['id'], 'switch-intent').exists())
        self.assertEqual({str(path):(path.stat().st_dev,path.stat().st_ino) for path in paths}, identities)
        moved.verify_artifact(artifact['id'])

    def test_existing_local_layer_cannot_be_silently_rewritten_through_shared_file(self):
        artifact, forward, moved = self.moved(); local = self.local(moved)
        shared = moved.config_path.read_bytes(); local_bytes = local.read_bytes()
        plan = moved.plan_reverse_relocation(forward['id'])
        self.assertEqual(plan['configuration_change']['target_path'], str(local))
        self.assertEqual(moved.config_path.read_bytes(), shared)
        self.assertEqual(local.read_bytes(), local_bytes)

    def test_tampered_return_layer_target_is_rejected(self):
        artifact, forward, moved = self.moved()
        plan = moved.plan_reverse_relocation(forward['id'])
        plan['configuration_change']['target_path'] = str(self.root / 'arbitrary.json')
        moved._path('relocations', plan['id']).write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'layer|stale|differs'):
            moved.prepare_reverse_relocation(plan['id'], 'owner', 'Return')
        self.assertFalse((self.root / 'arbitrary.json').exists())

    def test_recovery_and_rollback_refuse_local_drift_after_interrupted_exchange(self):
        from unittest.mock import patch
        import delivery_lifecycle
        artifact, forward, moved, plan, run = self.reverse()
        original = delivery_lifecycle.apply_directory_change
        def interrupted(change):
            original(change)
            raise OSError('Injected after first exchange')
        with patch('delivery_lifecycle.apply_directory_change', side_effect=interrupted):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(plan['id'], 'owner', 'Return')
        local = self.local(moved); config = moved.config_path.read_bytes()
        locations = [Path(root['staging']) for root in moved._read('relocations',plan['id'],'switch-intent')['roots']]
        identities = {str(path):(path.stat().st_dev,path.stat().st_ino) for path in locations if path.exists()}
        for operation in (moved.resume_reverse_relocation, moved.rollback_reverse_relocation):
            with self.assertRaisesRegex(ValueError, 'local|layer'):
                operation(plan['id'], 'owner', 'Recover')
            self.assertEqual(moved.config_path.read_bytes(), config)
            self.assertEqual({str(path):(path.stat().st_dev,path.stat().st_ino) for path in locations if path.exists()}, identities)
        local.unlink()
        result = moved.resume_reverse_relocation(plan['id'], 'owner', 'Resume reviewed layers')
        self.assertEqual(result['status'], 'SWITCHED')

    def test_forward_resume_and_rollback_refuse_new_local_file(self):
        from unittest.mock import patch
        artifact, plan = self.prepared()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Injected configuration write failure')):
            with self.assertRaises(OSError): self.store.switch_relocation(plan['id'], 'owner', 'Move')
        local = self.local(self.store); config = self.store.config_path.read_bytes()
        for operation in (self.store.resume_relocation, self.store.rollback_relocation):
            with self.assertRaisesRegex(ValueError, 'local|layer'):
                operation(plan['id'], 'owner', 'Recover')
            self.assertEqual(self.store.config_path.read_bytes(), config)
        self.assertTrue(local.exists())
        local.unlink()
        self.assertEqual(self.store.resume_relocation(plan['id'], 'owner', 'Resume reviewed layers')['status'], 'SWITCHED')
