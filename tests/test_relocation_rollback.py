"""Interrupted switches can restore exact configuration without deleting targets."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class RelocationRollbackTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def interrupted(self):
        artifact, plan = self.prepared(); before = self.store.config_path.read_bytes()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Write failed')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        return artifact, plan, before

    def test_rollback_releases_source_and_preserves_inactive_targets(self):
        artifact, plan, before = self.interrupted()
        result = self.store.rollback_relocation(plan['id'], 'owner', 'Recover interrupted switch')
        self.assertEqual(result['status'], 'ROLLED_BACK')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.store.verify_artifact(artifact['id']); self.store.start_run({})
        target = Lifecycle(self.root, {**self.cfg, 'storage': self.targets()})
        with self.assertRaisesRegex(ValueError, 'inactive'):
            target.start_run({})
        self.assertTrue(target.object_path(artifact['sha256']).exists())
        self.assertEqual(self.store.rollback_relocation(plan['id'], 'owner', 'Repeat'), result)

    def test_modified_source_prevents_rollback_and_keeps_fence(self):
        artifact, plan, _ = self.interrupted()
        (self.store.paths.workspace / artifact['workspace_path']).write_bytes(b'modified')
        with self.assertRaisesRegex(ValueError, 'source'):
            self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.start_run({})

    def test_user_configuration_edit_is_never_overwritten(self):
        _, plan, _ = self.interrupted()
        self.store.config_path.write_text(json.dumps({**self.cfg, 'headline': 'User change'}))
        before = self.store.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'configuration'):
            self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(self.store.config_path.read_bytes(), before)

    def test_failure_after_configuration_switch_restores_exact_original_bytes(self):
        artifact, plan = self.prepared(); before = self.store.config_path.read_bytes()
        original_write = self.store._write_path
        def fail_binding(path, data):
            if Path(path).parent.name == 'storage-bindings':
                raise OSError('Binding commit interrupted')
            return original_write(path, data)
        with patch.object(self.store, '_write_path', side_effect=fail_binding):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertNotEqual(self.store.config_path.read_bytes(), before)
        self.store.rollback_relocation(plan['id'], 'owner', 'Rollback interrupted commit')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.store.verify_artifact(artifact['id']); self.store.start_run({})

    def test_partial_directory_publish_can_rollback_without_removing_copies(self):
        artifact, plan = self.prepared()
        from delivery_lifecycle import commit_directory
        published = []
        def fail_second(source, destination):
            if published:
                raise OSError('Second root publication failed')
            commit_directory(source, destination); published.append(Path(destination))
        with patch('delivery_lifecycle.commit_directory', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.store.rollback_relocation(plan['id'], 'owner', 'Rollback partial publication')
        self.assertTrue(published[0].exists())
        self.store.verify_artifact(artifact['id']); self.store.start_run({})
