"""Reverse plans bind active bytes and protect occupied original roots."""
import json
from pathlib import Path
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class ReverseRelocationPlanTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def moved(self):
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        return artifact, plan, moved

    def test_reverse_plan_binds_new_active_data_without_changing_original(self):
        artifact, forward, moved = self.moved()
        run = moved.start_run({})
        before = self.store.config_path.read_bytes()
        reverse = moved.plan_reverse_relocation(forward['id'])
        self.assertEqual(reverse['operation'], 'reverse-relocation-plan')
        self.assertEqual(reverse['from'], forward['to'])
        self.assertEqual(reverse['to'], forward['from'])
        self.assertFalse(reverse['relocation_executed'])
        self.assertTrue(any(item['path'] == 'records/runs/' + run['id'] + '.json' for item in reverse['files']))
        self.assertFalse(self.store._path('runs', run['id']).exists())
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertEqual(moved.verify_reverse_relocation_plan(reverse['id'])['status'], 'READY')

    def test_changed_original_copy_blocks_plan(self):
        artifact, forward, moved = self.moved()
        source = self.store.paths.workspace / artifact['workspace_path']
        source.write_bytes(b'Changed preserved copy')
        with self.assertRaisesRegex(ValueError, 'preserved source'):
            moved.plan_reverse_relocation(forward['id'])

    def test_unknown_original_file_blocks_plan(self):
        artifact, forward, moved = self.moved()
        (self.store.paths.workspace / 'owner-notes.txt').write_text('Keep this')
        with self.assertRaisesRegex(ValueError, 'preserved source'):
            moved.plan_reverse_relocation(forward['id'])

    def test_active_source_change_invalidates_reverse_plan(self):
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            moved.verify_reverse_relocation_plan(reverse['id'])

    def test_object_only_reverse_keeps_new_workspace_records(self):
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        storage = {**self.cfg['storage'], 'objectRoot': 'moved objects'}
        forward = self.store.plan_relocation(storage)
        self.store.prepare_relocation(forward['id'], 'owner', 'Move objects')
        self.store.switch_relocation(forward['id'], 'owner', 'Switch objects')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        run = moved.start_run({})
        attempt = moved.start_attempt(run['id'], 'render', 'owner')
        path = moved.work_path(attempt['id']) / 'new'
        path.write_bytes(b'New object after move')
        added = moved.register(attempt['id'], path, 'source')
        moved.finish_attempt(attempt['id'], 'succeeded')
        reverse = moved.plan_reverse_relocation(forward['id'])
        self.assertEqual(reverse['from']['workspace'], reverse['to']['workspace'])
        self.assertTrue(any(item['sha256'] == added['sha256'] for item in reverse['files']))
        self.assertEqual(moved.verify_reverse_relocation_plan(reverse['id'])['status'], 'READY')

    def test_prepare_reverse_copies_new_data_and_preserves_both_roots(self):
        artifact, forward, moved = self.moved()
        run = moved.start_run({})
        reverse = moved.plan_reverse_relocation(forward['id'])
        config_before = moved.config_path.read_bytes()
        prepared = moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare return')
        self.assertEqual(prepared['status'], 'PREPARED')
        self.assertEqual(moved.config_path.read_bytes(), config_before)
        self.assertTrue(self.store.object_path(artifact['sha256']).is_file())
        self.assertTrue(moved.object_path(artifact['sha256']).is_file())
        self.assertFalse(self.store._path('runs', run['id']).exists())
        self.assertTrue(any(Path(item['path']).name == run['id'] + '.json' for item in prepared['staged_files']))
        self.assertEqual(moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Repeat'), prepared)

    def test_preparation_refuses_stale_original_before_copying(self):
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        (self.store.paths.workspace / 'new-note').write_text('Preserve this')
        with self.assertRaisesRegex(ValueError, 'preserved source'):
            moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        self.assertFalse(moved._path('relocations', reverse['id'], 'prepare-intent').exists())

    def test_reverse_plan_cannot_use_forward_switch(self):
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        config_before = moved.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'dedicated execution'):
            moved.switch_relocation(reverse['id'], 'owner', 'Wrong operation')
        self.assertEqual(moved.config_path.read_bytes(), config_before)
        moved.start_run({})

    def test_changed_staging_refuses_repeated_preparation(self):
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        prepared = moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        path = next(Path(item['path']) for item in prepared['staged_files']
                    if Path(item['path']).name != '.relocation-owner.json')
        path.write_bytes(b'Tampered staging')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Retry')
        moved.verify_artifact(artifact['id'])

    def test_failed_reverse_preparation_recovers_without_losing_partial_files(self):
        from unittest.mock import patch
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        before = moved.config_path.read_bytes()
        with patch('relocation_lifecycle.shutil.copyfileobj', side_effect=OSError('Copy interrupted')):
            with self.assertRaisesRegex(OSError, 'Copy interrupted'):
                moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        intent = moved._read('relocations', reverse['id'], 'prepare-intent')
        stage = Path(next(iter(intent['staging'].values())))
        unknown = stage / 'partial-note'
        unknown.write_text('Keep failed evidence')
        recovery = moved.recover_relocation(reverse['id'], 'owner', 'Retry copy')
        retry = moved._read('relocations', recovery['retry_plan_id'])
        self.assertEqual(retry['operation'], 'reverse-relocation-plan')
        self.assertEqual(moved.prepare_reverse_relocation(retry['id'], 'owner', 'Retry')['status'], 'PREPARED')
        self.assertEqual(unknown.read_text(), 'Keep failed evidence')
        self.assertEqual(moved.config_path.read_bytes(), before)
        moved.verify_artifact(artifact['id'])

    def test_cancelled_partial_reverse_reports_retained_evidence(self):
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        prepared = moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        unknown = Path(next(iter(prepared['staging'].values()))) / 'keep-note'
        unknown.write_text('Keep this')
        cancelled = moved.cancel_relocation(reverse['id'], 'owner', 'Cancel')
        self.assertEqual(cancelled['status'], 'CANCELLED_PARTIAL')
        status = moved.relocation_status(reverse['id'])
        self.assertEqual(status['status'], 'CANCELLED_PARTIAL')
        self.assertIn(str(unknown), status['retained_paths'])
        self.assertEqual(unknown.read_text(), 'Keep this')
        moved.verify_artifact(artifact['id'])

    def test_reverse_preparation_binds_occupied_directory_identities(self):
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        prepared = moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        roots = prepared['exchange_roots']
        self.assertTrue(roots)
        for root in roots:
            staged = Path(root['staging']).stat()
            self.assertEqual(root['staging_identity'], [staged.st_dev, staged.st_ino])
            if root['operation'] == 'EXCHANGE':
                original = Path(root['destination']).stat()
                self.assertEqual(root['destination_identity'], [original.st_dev, original.st_ino])
            else:
                self.assertEqual(root['operation'], 'PUBLISH')
                self.assertIsNone(root['destination_identity'])
                self.assertFalse(Path(root['destination']).exists())

    def test_same_bytes_replaced_original_root_refuses_prepared_reuse(self):
        import shutil
        artifact, forward, moved = self.moved()
        reverse = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Prepare')
        original = self.store.paths.workspace
        displaced = original.with_name(original.name + '-displaced')
        original.rename(displaced)
        shutil.copytree(displaced, original)
        with self.assertRaisesRegex(ValueError, 'directory identity'):
            moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Retry')
        self.assertTrue(displaced.is_dir())
