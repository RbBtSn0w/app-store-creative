"""Interrupted relocation recovery preserves quarantine copy identity fences."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_quarantine_location_projection as fixtures
from artifact_lifecycle import Lifecycle


class QuarantineLocationRecoveryTests(unittest.TestCase):
    setUp = fixtures.QuarantineLocationProjectionTests.setUp
    source = fixtures.QuarantineLocationProjectionTests.source
    targets = fixtures.QuarantineLocationProjectionTests.targets
    prepared = fixtures.QuarantineLocationProjectionTests.prepared
    moved = fixtures.QuarantineLocationProjectionTests.moved
    planned = fixtures.QuarantineLocationProjectionTests.planned
    staged = fixtures.QuarantineLocationProjectionTests.staged
    next_roots = fixtures.QuarantineLocationProjectionTests.next_roots
    relocated = fixtures.QuarantineLocationProjectionTests.relocated
    row = fixtures.QuarantineLocationProjectionTests.row

    def interrupted_forward(self):
        import delivery_lifecycle
        core, receipt, artifact = self.staged()
        core.cancel_relocation_quarantine_preparation(receipt['id'], 'owner', 'Keep copies')
        plan = core.plan_relocation(self.next_roots())
        core.prepare_relocation(plan['id'], 'owner', 'Move')
        original = delivery_lifecycle.commit_directory
        def publish(source, destination):
            result = original(source, destination)
            if Path(destination) == Path(plan['to']['workspace']):
                raise OSError('After workspace publication')
            return result
        with patch('delivery_lifecycle.commit_directory', side_effect=publish):
            with self.assertRaises(OSError):
                core.switch_relocation(plan['id'], 'owner', 'Move')
        return core, receipt, artifact, plan

    def replace_payload(self, plan, receipt):
        root = Path(plan['to']['workspace']) / 'maintenance/relocation-quarantine' / receipt['id']
        payload = next(root.iterdir())
        replacement = payload.with_name('replacement'); replacement.write_bytes(payload.read_bytes()); replacement.replace(payload)

    def test_forward_resume_rejects_same_byte_replacement_in_published_workspace(self):
        core, receipt, artifact, plan = self.interrupted_forward()
        before = core.config_path.read_bytes()
        self.replace_payload(plan, receipt)
        with self.assertRaisesRegex(ValueError, '[Qq]uarantine location proof differs'):
            core.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(core.config_path.read_bytes(), before)
        self.assertFalse(core._path('relocations', plan['id'], 'switched').exists())

    def test_unchanged_forward_resume_preserves_verified_inventory(self):
        core, receipt, artifact, plan = self.interrupted_forward()
        core.resume_relocation(plan['id'], 'owner', 'Resume')
        current = Lifecycle(self.root, json.loads(core.config_path.read_text()))
        self.assertEqual(self.row(current)['status'], 'VERIFIED')
        current.verify_artifact(artifact['id'])

    def interrupted_reverse(self, after_workspace=False):
        import delivery_lifecycle
        core, receipt, artifact, forward = self.relocated()
        plan = core.plan_reverse_relocation(forward['id'])
        core.prepare_reverse_relocation(plan['id'], 'owner', 'Return')
        original = delivery_lifecycle.apply_directory_change
        changed = []
        def exchange(change):
            result = original(change)
            if not changed and (not after_workspace or Path(change['destination']) == Path(plan['to']['workspace'])):
                changed.append(True)
                raise OSError('After root exchange')
            return result
        with patch('delivery_lifecycle.apply_directory_change', side_effect=exchange):
            with self.assertRaises(OSError):
                core.switch_reverse_relocation(plan['id'], 'owner', 'Return')
        return core, receipt, artifact, plan

    def test_reverse_resume_rejects_same_byte_replacement_after_exchange(self):
        core, receipt, artifact, plan = self.interrupted_reverse()
        before = core.config_path.read_bytes()
        self.replace_payload(plan, receipt)
        with self.assertRaisesRegex(ValueError, '[Qq]uarantine location proof differs'):
            core.resume_reverse_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(core.config_path.read_bytes(), before)

    def test_reverse_rollback_rejects_same_byte_replacement_after_exchange(self):
        core, receipt, artifact, plan = self.interrupted_reverse()
        before = core.config_path.read_bytes()
        self.replace_payload(plan, receipt)
        with self.assertRaisesRegex(ValueError, '[Qq]uarantine location proof differs'):
            core.rollback_reverse_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(core.config_path.read_bytes(), before)

    def test_unchanged_reverse_resume_preserves_verified_inventory(self):
        core, receipt, artifact, plan = self.interrupted_reverse()
        core.resume_reverse_relocation(plan['id'], 'owner', 'Resume')
        current = Lifecycle(self.root, json.loads(core.config_path.read_text()))
        self.assertEqual(self.row(current)['status'], 'VERIFIED')
        current.verify_artifact(artifact['id'])

    def test_unchanged_reverse_rollback_keeps_source_and_copy_evidence(self):
        core, receipt, artifact, plan = self.interrupted_reverse()
        before = core.config_path.read_bytes()
        core.rollback_reverse_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(core.config_path.read_bytes(), before)
        self.assertEqual(self.row(core)['status'], 'VERIFIED')
        core.verify_artifact(artifact['id'])
        core.start_run({})

    def test_forward_resume_preserves_unknown_file_and_refuses_mutation(self):
        core, receipt, artifact, plan = self.interrupted_forward()
        note = Path(plan['to']['workspace']) / 'maintenance/relocation-quarantine' / receipt['id'] / 'owner-note'
        note.write_text('Keep')
        before = core.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, '[Qq]uarantine location proof differs'):
            core.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(note.read_text(), 'Keep')
        self.assertEqual(core.config_path.read_bytes(), before)

    def test_reverse_resume_checks_published_copy_after_workspace_exchange(self):
        core, receipt, artifact, plan = self.interrupted_reverse(after_workspace=True)
        self.replace_payload(plan, receipt)
        before = core.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'quarantine location proof differs'):
            core.resume_reverse_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(core.config_path.read_bytes(), before)

    def test_reverse_rollback_checks_published_copy_after_workspace_exchange(self):
        core, receipt, artifact, plan = self.interrupted_reverse(after_workspace=True)
        self.replace_payload(plan, receipt)
        before = core.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'quarantine location proof differs'):
            core.rollback_reverse_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(core.config_path.read_bytes(), before)
