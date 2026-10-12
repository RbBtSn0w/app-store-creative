"""Repeated migration keeps historical bindings after an activated return."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_reverse_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle, canonical


class RepeatedRelocationTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationSwitchTests.setUp
    source = fixtures.ReverseRelocationSwitchTests.source
    targets = fixtures.ReverseRelocationSwitchTests.targets
    prepared = fixtures.ReverseRelocationSwitchTests.prepared
    moved = fixtures.ReverseRelocationSwitchTests.moved
    reverse = fixtures.ReverseRelocationSwitchTests.reverse

    def returned(self, shared=False):
        if shared:
            self.targets = lambda: {**self.cfg['storage'], 'objectRoot': 'second objects'}
        artifact, forward, moved, reverse, run = self.reverse()
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        original = returned._read('storage-bindings', hashlib.sha256(canonical(forward['from'])).hexdigest())
        storage = ({**returned.config['storage'], 'objectRoot': 'third objects'} if shared else
                   {'workspaceRoot': 'third work', 'objectRoot': 'third objects',
                    'releaseRoot': 'third deliveries', 'publicationRoot': 'third publications'})
        plan = returned.plan_relocation(storage)
        returned.prepare_relocation(plan['id'], 'owner', 'Move again')
        return artifact, forward, returned, plan, run, original

    def verify_target(self, returned, artifact, run, forward):
        target = Lifecycle(self.root, json.loads(returned.config_path.read_text()))
        target.verify_artifact(artifact['id']); target._run(run['id']); target.start_run({})
        self.assertEqual(target.resolve_storage_binding(forward['from']), target.paths.binding())
        self.assertEqual(target.resolve_storage_binding(forward['to']), target.paths.binding())
        return target

    def test_migrate_after_return_preserves_old_binding_evidence(self):
        artifact, forward, returned, plan, run, original = self.returned()
        returned.switch_relocation(plan['id'], 'owner', 'Move again')
        target = self.verify_target(returned, artifact, run, forward)
        histories = list((target.paths.workspace / 'records/relocations' / plan['id'] / 'control-history/storage-bindings').glob('*.json'))
        self.assertEqual(len(histories), 1)
        self.assertEqual(json.loads(histories[0].read_text())['before'], original)

    def test_resume_after_configuration_sync_failure_preserves_old_bindings(self):
        artifact, forward, returned, plan, run, original = self.returned()
        with patch.object(returned, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Sync interrupted'):
                returned.switch_relocation(plan['id'], 'owner', 'Move again')
        returned.resume_relocation(plan['id'], 'owner', 'Resume')
        self.verify_target(returned, artifact, run, forward)

    def test_object_only_migration_after_return_keeps_shared_workspace(self):
        artifact, forward, returned, plan, run, original = self.returned(shared=True)
        returned.switch_relocation(plan['id'], 'owner', 'Move again')
        target = self.verify_target(returned, artifact, run, forward)
        self.assertEqual(target.paths.workspace, returned.paths.workspace)

    def test_shared_workspace_resume_after_binding_updated(self):
        artifact, forward, returned, plan, run, original = self.returned(shared=True)
        original_write = returned._write_path
        def interrupted(path, data):
            if path == returned._path('relocations', plan['id'], 'switched'):
                raise OSError('Receipt interrupted')
            return original_write(path, data)
        with patch.object(returned, '_write_path', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'Receipt interrupted'):
                returned.switch_relocation(plan['id'], 'owner', 'Move again')
        returned.resume_relocation(plan['id'], 'owner', 'Resume')
        self.verify_target(returned, artifact, run, forward)

    def test_shared_workspace_rollback_after_binding_updated_restores_predecessor(self):
        artifact, forward, returned, plan, run, original = self.returned(shared=True)
        original_write = returned._write_path
        def interrupted(path, data):
            if path == returned._path('relocations', plan['id'], 'switched'):
                raise OSError('Receipt interrupted')
            return original_write(path, data)
        with patch.object(returned, '_write_path', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'Receipt interrupted'):
                returned.switch_relocation(plan['id'], 'owner', 'Move again')
        returned.rollback_relocation(plan['id'], 'owner', 'Keep source')
        active = Lifecycle(self.root, json.loads(returned.config_path.read_text()))
        active.verify_artifact(artifact['id']); active._run(run['id']); active.start_run({})
        self.assertEqual(active._read('storage-bindings', original['id']), original)

    def test_resume_rejects_tampered_predecessor_before_further_writes(self):
        artifact, forward, returned, plan, run, original = self.returned()
        with patch.object(returned, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Sync interrupted'):
                returned.switch_relocation(plan['id'], 'owner', 'Move again')
        path = returned._path('relocations', plan['id'], 'switch-intent')
        intent = json.loads(path.read_text())
        intent['storage_controls']['storage-bindings']['before']['switch_sha256'] = 'c' * 64
        path.write_bytes(canonical(intent))
        before = returned.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'predecessor differs from plan'):
            returned.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(returned.config_path.read_bytes(), before)
        self.assertFalse((Path(plan['to']['workspace']) / 'records/relocations' / plan['id'] / 'switched.json').exists())
