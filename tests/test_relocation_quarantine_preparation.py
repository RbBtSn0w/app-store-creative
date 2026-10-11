"""Quarantine preparation persists verified recovery bytes before any source removal."""
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_retention_plan as fixtures


class RelocationQuarantinePreparationTests(unittest.TestCase):
    setUp = fixtures.RelocationRetentionPlanTests.setUp
    source = fixtures.RelocationRetentionPlanTests.source
    targets = fixtures.RelocationRetentionPlanTests.targets
    prepared = fixtures.RelocationRetentionPlanTests.prepared
    moved = fixtures.RelocationRetentionPlanTests.moved

    def planned(self):
        active, move, artifact = self.moved()
        return active, active.plan_relocation_retention(retention_days=0), artifact

    def test_preparation_copies_media_and_keeps_source(self):
        active, plan, artifact = self.planned()
        result = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        self.assertEqual(result['status'], 'PREPARED')
        self.assertEqual(len(result['copies']), 1)
        payload = Path(result['copies'][0]['quarantine_path'])
        self.assertEqual(payload.read_bytes(), self.store.object_path(artifact['sha256']).read_bytes())
        self.assertEqual(active.verify_relocation_retention(plan['id'])['status'], 'READY')
        self.assertFalse(result['source_removal_executed'])

    def test_stale_plan_refuses_before_operation_creation(self):
        active, plan, artifact = self.planned()
        active.start_run({})
        with self.assertRaisesRegex(ValueError, 'stale'):
            active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        operations = [active._read('maintenance', path.stem) for path in (active.paths.workspace / 'records/maintenance').glob('*.json')]
        self.assertFalse(any(item['operation'] == 'relocation-quarantine' for item in operations))

    def test_preparation_requires_actor_and_reason(self):
        active, plan, artifact = self.planned()
        for actor, reason in [('', 'Reason'), ('owner', ' '), (True, 'Reason')]:
            with self.assertRaises(ValueError):
                active.prepare_relocation_quarantine(plan['id'], actor, reason)

    def test_completed_preparation_resumes_without_rewriting_payload(self):
        active, plan, artifact = self.planned()
        result = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        payload = Path(result['copies'][0]['quarantine_path']); before = payload.stat().st_ino
        resumed = active.resume_relocation_quarantine_preparation(result['id'], 'owner', 'Resume')
        self.assertEqual(resumed, result)
        self.assertEqual(payload.stat().st_ino, before)

    def operation(self, active):
        return next(active._read('maintenance', path.stem)
                    for path in (active.paths.workspace / 'records/maintenance').glob('*.json')
                    if active._read('maintenance', path.stem)['operation'] == 'relocation-quarantine')

    def test_partial_copy_preserved_and_resume_refuses_overwrite(self):
        active, plan, artifact = self.planned()
        def partial(source, target):
            target.write(b'part'); target.flush()
            raise OSError('Copy interrupted')
        with patch('relocation_quarantine.shutil.copyfileobj', side_effect=partial):
            with self.assertRaisesRegex(OSError, 'Copy interrupted'):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        operation = self.operation(active)
        failure = active._read('maintenance', operation['id'], 'preparation-failure')
        self.assertEqual(failure['status'], 'INTERRUPTED')
        self.assertEqual(failure['error_type'], 'OSError')
        payload = next(Path(operation['quarantine_root']).iterdir())
        self.assertEqual(payload.read_bytes(), b'part')
        with self.assertRaisesRegex(ValueError, 'Partial or corrupt'):
            active.resume_relocation_quarantine_preparation(operation['id'], 'owner', 'Resume')
        self.assertEqual(payload.read_bytes(), b'part')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())
        self.assertFalse(active._path('maintenance', operation['id'], 'prepared').exists())

    def test_complete_payload_sync_interruption_can_resume(self):
        import relocation_quarantine
        active, plan, artifact = self.planned()
        original = relocation_quarantine._sync_history
        def sync(path, workspace):
            if Path(path).parent.parent.name == 'relocation-quarantine' and Path(path).name.endswith(artifact['sha256']):
                raise OSError('Payload sync interrupted')
            original(path, workspace)
        with patch('relocation_quarantine._sync_history', side_effect=sync):
            with self.assertRaisesRegex(OSError, 'Payload sync interrupted'):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        operation = self.operation(active)
        result = active.resume_relocation_quarantine_preparation(operation['id'], 'owner', 'Resume')
        self.assertEqual(result['status'], 'PREPARED')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_same_bytes_quarantine_replacement_refuses_resume(self):
        import shutil
        active, plan, artifact = self.planned()
        result = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        payload = Path(result['copies'][0]['quarantine_path']); kept = payload.parent.parent / 'kept'
        payload.rename(kept); shutil.copy2(kept, payload)
        with self.assertRaisesRegex(ValueError, 'ownership changed'):
            active.resume_relocation_quarantine_preparation(result['id'], 'owner', 'Resume')
        self.assertTrue(kept.exists())

    def test_quarantine_directory_alias_refuses_resume(self):
        active, plan, artifact = self.planned()
        result = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        root = Path(result['copies'][0]['quarantine_path']).parent
        kept = root.with_name('kept'); root.rename(kept); root.symlink_to(kept)
        with self.assertRaisesRegex(ValueError, 'aliases'):
            active.resume_relocation_quarantine_preparation(result['id'], 'owner', 'Resume')

    def test_configuration_changes_during_copy_refuse_prepared_receipt(self):
        import json
        import shutil
        active, plan, artifact = self.planned()
        original = shutil.copyfileobj
        def copy(source, target):
            original(source, target)
            config = json.loads(active.config_path.read_text()); config['note'] = 'Changed during preparation'
            active.config_path.write_text(json.dumps(config))
        with patch('relocation_quarantine.shutil.copyfileobj', side_effect=copy):
            with self.assertRaisesRegex(ValueError, 'stale'):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        operation = self.operation(active)
        self.assertFalse(active._path('maintenance', operation['id'], 'prepared').exists())
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_replacement_during_copy_refuses_prepared_receipt(self):
        import shutil
        active, plan, artifact = self.planned()
        original = shutil.copyfileobj
        def copy(source, target):
            original(source, target); target.flush()
            operation = self.operation(active)
            payload = next(Path(operation['quarantine_root']).iterdir())
            kept = payload.with_name('kept'); payload.rename(kept); shutil.copy2(kept, payload); kept.unlink()
        with patch('relocation_quarantine.shutil.copyfileobj', side_effect=copy):
            with self.assertRaisesRegex(ValueError, 'ownership changed'):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_unknown_quarantine_file_preserved_and_blocks_resume(self):
        active, plan, artifact = self.planned()
        result = active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        note = Path(result['copies'][0]['quarantine_path']).parent / 'owner-note'; note.write_text('Keep')
        with self.assertRaisesRegex(ValueError, 'unknown files'):
            active.resume_relocation_quarantine_preparation(result['id'], 'owner', 'Resume')
        self.assertEqual(note.read_text(), 'Keep')

    def test_directory_replacement_at_file_creation_does_not_write_replacement(self):
        import os
        active, plan, artifact = self.planned()
        replacement = self.root / 'unmanaged'; replacement.mkdir()
        original_open = os.open
        swapped = False
        def opening(path, flags, *args, **kwargs):
            nonlocal swapped
            if flags & os.O_CREAT and artifact['sha256'] in str(path) and not swapped:
                swapped = True
                operation = self.operation(active); root = Path(operation['quarantine_root'])
                root.rename(root.with_name('retained-original')); root.symlink_to(replacement)
            return original_open(path, flags, *args, **kwargs)
        with patch('relocation_quarantine.os.open', side_effect=opening):
            with self.assertRaises(ValueError):
                active.prepare_relocation_quarantine(plan['id'], 'owner', 'Expired backup')
        self.assertTrue(swapped)
        self.assertEqual(list(replacement.iterdir()), [])
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())
