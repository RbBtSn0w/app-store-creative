"""Activated reversals can revisit roots without losing immutable evidence."""
import json
import unittest
from unittest.mock import patch
import test_repeated_relocation as fixtures
from artifact_lifecycle import Lifecycle


class ReverseRelocationCycleTests(unittest.TestCase):
    setUp = fixtures.RepeatedRelocationTests.setUp
    source = fixtures.RepeatedRelocationTests.source
    targets = fixtures.RepeatedRelocationTests.targets
    prepared = fixtures.RepeatedRelocationTests.prepared
    moved = fixtures.RepeatedRelocationTests.moved
    reverse = fixtures.RepeatedRelocationTests.reverse
    returned = fixtures.RepeatedRelocationTests.returned

    def next_return(self, shared=False):
        artifact, first, active, outward, run, original = self.returned(shared)
        active.switch_relocation(outward['id'], 'owner', 'Move again')
        moved = Lifecycle(self.root, json.loads(active.config_path.read_text()))
        latest = moved.start_run({})
        returning = moved.plan_reverse_relocation(outward['id'])
        moved.prepare_reverse_relocation(returning['id'], 'owner', 'Return again')
        return artifact, first, moved, returning, run, latest

    def check(self, moved, artifact, run, latest):
        active = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        active.verify_artifact(artifact['id']); active._run(run['id']); active._run(latest['id'])
        active.start_run({})
        return active

    def test_copied_object_inspection_after_repeated_return(self):
        artifact, first, moved, returning, run, latest = self.next_return()
        moved.switch_reverse_relocation(returning['id'], 'fixture-owner', 'Return again')
        active = self.check(moved, artifact, run, latest)
        result = active.relocated_object_status(returning['id'])
        self.assertEqual(result['status'], 'PASS', result)
        self.assertTrue(result['object_integrity_verified'])

    def test_return_after_second_outward_migration_replaces_old_activation(self):
        artifact, first, moved, returning, run, latest = self.next_return()
        moved.switch_reverse_relocation(returning['id'], 'owner', 'Return again')
        active = self.check(moved, artifact, run, latest)
        self.assertEqual(active.paths.binding(), first['from'])
        histories = list((active.paths.workspace / 'records/relocations' / returning['id'] / 'control-history/storage-activations').glob('*.json'))
        self.assertEqual(len(histories), 1)
        self.assertIsNotNone(json.loads(histories[0].read_text())['before'])

    def test_repeated_return_can_resume_after_exchange(self):
        artifact, first, moved, returning, run, latest = self.next_return()
        import delivery_lifecycle
        original = delivery_lifecycle.apply_directory_change
        def interrupt(change):
            original(change)
            raise OSError('Exchange interrupted')
        with patch('delivery_lifecycle.apply_directory_change', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'Exchange interrupted'):
                moved.switch_reverse_relocation(returning['id'], 'owner', 'Return again')
        moved.resume_reverse_relocation(returning['id'], 'owner', 'Resume')
        self.check(moved, artifact, run, latest)

    def test_shared_workspace_repeated_return_rollback_restores_prior_controls(self):
        artifact, first, moved, returning, run, latest = self.next_return(shared=True)
        before = {str(path): path.read_bytes() for category in ('storage-activations', 'storage-bindings')
                  for path in (moved.paths.workspace / 'records' / category).glob('*.json')}
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Config sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Config sync interrupted'):
                moved.switch_reverse_relocation(returning['id'], 'owner', 'Return again')
        moved.rollback_reverse_relocation(returning['id'], 'owner', 'Keep source')
        after = {str(path): path.read_bytes() for category in ('storage-activations', 'storage-bindings')
                 for path in (moved.paths.workspace / 'records' / category).glob('*.json')}
        self.assertEqual(before, after)
        self.check(moved, artifact, run, latest)

    def cycles(self, shared=False):
        if shared:
            self.targets = lambda: {**self.cfg["storage"], "objectRoot": "second objects"}
        artifact, outward, active = self.moved()
        runs = []
        operation = outward
        for index in range(4):
            runs.append(active.start_run({})['id'])
            returning = active.plan_reverse_relocation(operation['id'])
            active.prepare_reverse_relocation(returning['id'], 'owner', 'Cycle')
            active.switch_reverse_relocation(returning['id'], 'owner', 'Cycle')
            active = Lifecycle(self.root, json.loads(active.config_path.read_text()))
            active.verify_artifact(artifact['id'])
            for run in runs:
                active._run(run)
            self.assertEqual(active.paths.binding(), outward['from' if index % 2 == 0 else 'to'])
            operation = returning

    def test_multiple_activated_reverse_cycles_keep_all_runs(self):
        self.cycles()

    def test_shared_workspace_supports_multiple_activated_reverse_cycles(self):
        self.cycles(shared=True)

    def test_repeated_return_resumes_after_configuration_changed(self):
        artifact, first, moved, returning, run, latest = self.next_return(shared=True)
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Config sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Config sync interrupted'):
                moved.switch_reverse_relocation(returning['id'], 'owner', 'Return again')
        moved.resume_reverse_relocation(returning['id'], 'owner', 'Resume')
        self.check(moved, artifact, run, latest)

    def test_modified_replaced_activation_refuses_resume_and_preserves_fence(self):
        artifact, first, moved, returning, run, latest = self.next_return(shared=True)
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Config sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Config sync interrupted'):
                moved.switch_reverse_relocation(returning['id'], 'owner', 'Return again')
        intent = moved._read('relocations', returning['id'], 'switch-intent')
        activation = moved.paths.workspace / 'records/storage-activations' / (intent['activation']['id'] + '.json')
        altered = json.loads(activation.read_text()); altered['switch_sha256'] = 'c' * 64
        from artifact_lifecycle import canonical
        activation.write_bytes(canonical(altered))
        before = moved.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'precondition'):
            moved.resume_reverse_relocation(returning['id'], 'owner', 'Resume')
        self.assertEqual(moved.config_path.read_bytes(), before)
        self.assertEqual(activation.read_bytes(), canonical(altered))
        with self.assertRaisesRegex(ValueError, 'fenced'):
            moved.start_run({})

    def test_foreign_project_preserved_fence_cannot_authorize_reverse_plan(self):
        import hashlib
        from artifact_lifecycle import canonical
        artifact, outward, moved = self.moved()
        key = hashlib.sha256(canonical(outward['from'])).hexdigest()
        for core in (self.store, moved):
            path = core._path('storage-fences', key, outward['id'])
            fence = json.loads(path.read_text()); fence['project_id'] = 'foreign-project'
            path.write_bytes(canonical(fence))
        before = moved.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'preserved source fence'):
            moved.plan_reverse_relocation(outward['id'])
        self.assertEqual(moved.config_path.read_bytes(), before)
