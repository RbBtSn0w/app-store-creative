"""Sealing must consume approval bytes bound to their persisted commit intent."""
import json
import unittest
import test_delivery_lifecycle as fixtures


class ApprovalCommitIntegrityTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_changed_approval_actor_cannot_authorize_sealing(self):
        validation, approval = self.approved()
        path = self.store._path('approvals', approval['id'])
        changed = json.loads(path.read_text()); changed['actor'] = 'different-actor'
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'commit|binding|integrity'):
            self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(json.loads(path.read_text()), changed)
        self.assertEqual(list((self.store.paths.workspace / 'records/deliveries').glob('*.json')), [])

    def test_missing_approval_event_cannot_authorize_sealing(self):
        validation, approval = self.approved()
        event = self.store._path('events', approval['_commit_event_id'])
        event.unlink()
        before = self.store._path('approvals', approval['id']).read_bytes()
        with self.assertRaisesRegex(ValueError, 'commit event is missing'):
            self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(self.store._path('approvals', approval['id']).read_bytes(), before)
        self.assertFalse(event.exists())

    def test_damaged_approval_remains_auditable_and_blocks_cleanup(self):
        _, approval = self.approved()
        path = self.store._path('approvals', approval['id'])
        changed = json.loads(path.read_text()); changed['actor'] = 'different-actor'
        path.write_text(json.dumps(changed))
        before = {str(p): p.read_bytes() for root in (self.store.paths.workspace, self.store.paths.objects)
                  for p in root.rglob('*') if p.is_file()}
        history = self.store.verify_history()
        self.assertEqual(history['status'], 'FAIL')
        row = next(row for row in history['events'] if row['event_id'] == approval['_commit_event_id'])
        self.assertEqual(row['status'], 'CHANGED')
        with self.assertRaisesRegex(ValueError, 'commit|binding|integrity'):
            self.store.plan_cleanup(retention_days=0)
        after = {str(p): p.read_bytes() for root in (self.store.paths.workspace, self.store.paths.objects)
                 for p in root.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_valid_approval_remains_usable_after_workspace_relocation(self):
        from artifact_lifecycle import Lifecycle
        validation, approval = self.approved()
        self.store.config_path.write_text(json.dumps(self.config))
        plan = self.store.plan_relocation({'workspaceRoot':'next/work','objectRoot':'next/media',
                                         'releaseRoot':'next/releases','publicationRoot':'next/publications'})
        self.store.prepare_relocation(plan['id'], 'fixture-owner', 'Move approved fixture')
        self.store.switch_relocation(plan['id'], 'fixture-owner', 'Move approved fixture')
        moved = Lifecycle.from_configuration(self.root, self.store.config_path)
        self.assertEqual(moved._read('approvals', approval['id']), approval)
        delivery = moved.seal(self.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(moved.delivery_status(delivery['id'])['local_status'], 'PASS')
