"""Location projections retain their immutable predecessor on replacement."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import canonical


class StorageControlProjectionTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def records(self):
        binding = self.store.paths.binding()
        key = hashlib.sha256(canonical(binding)).hexdigest()
        before = {'schema_version': 1, 'id': key, 'to': binding,
                  'relocation_id': 'old-operation', 'switch_sha256': 'a' * 64}
        after = {**before, 'relocation_id': 'new-operation', 'switch_sha256': 'b' * 64}
        return key, before, after

    def publish(self, key, before, after, **options):
        from storage_control_projection import publish
        return publish(self.store, self.store.paths.workspace, 'new-operation',
                       'storage-activations', key, before, after, **options)

    def test_replace_retains_previous_bytes_and_retry_is_idempotent(self):
        key, before, after = self.records()
        path = self.store._path('storage-activations', key)
        self.store._write_path(path, before)
        result = self.publish(key, before, after)
        self.assertEqual(path.read_bytes(), canonical(after))
        history = Path(result['journal_path'])
        import json
        journal = json.loads(history.read_text())
        self.assertEqual(journal['before'], before)
        self.assertEqual(journal['after'], after)
        snapshot = history.read_bytes()
        self.publish(key, before, after)
        self.assertEqual(history.read_bytes(), snapshot)

    def test_changed_predecessor_refuses_before_journal_or_replacement(self):
        key, before, after = self.records()
        path = self.store._path('storage-activations', key)
        modified = {**before, 'switch_sha256': 'c' * 64}
        self.store._write_path(path, modified)
        with self.assertRaisesRegex(ValueError, 'precondition'):
            self.publish(key, before, after)
        self.assertEqual(path.read_bytes(), canonical(modified))
        self.assertFalse((self.store.paths.workspace / 'records/relocations/new-operation').exists())

    def test_initial_creation_retries_and_rejects_new_intent(self):
        key, before, after = self.records()
        self.publish(key, None, after)
        self.publish(key, None, after)
        with self.assertRaisesRegex(ValueError, 'journal'):
            self.publish(key, None, before)
        self.assertEqual(self.store._path('storage-activations', key).read_bytes(), canonical(after))

    def test_failure_after_replace_retains_history_and_retry_syncs(self):
        key, before, after = self.records()
        path = self.store._path('storage-activations', key)
        self.store._write_path(path, before)
        import storage_control_projection as module
        original = module._sync
        def fail(directory):
            if directory == path.parent:
                raise OSError('Projection sync interrupted')
            original(directory)
        with patch('storage_control_projection._sync', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'sync interrupted'):
                self.publish(key, before, after)
        self.assertEqual(path.read_bytes(), canonical(after))
        self.publish(key, before, after)

    def test_foreign_change_after_journal_refuses_replacement(self):
        key, before, after = self.records()
        path = self.store._path('storage-activations', key)
        self.store._write_path(path, before)
        import storage_control_projection as module
        original = module._sync_history
        def mutate(history, workspace):
            original(history, workspace)
            path.write_bytes(canonical({**before, 'switch_sha256': 'c' * 64}))
        with patch('storage_control_projection._sync_history', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'precondition'):
                self.publish(key, before, after)
        self.assertNotEqual(path.read_bytes(), canonical(after))

    def test_alias_refused_without_modifying_external_record(self):
        key, before, after = self.records()
        external = self.root / 'external.json'; external.write_bytes(canonical(before))
        path = self.store._path('storage-activations', key)
        path.parent.mkdir(parents=True); path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.publish(key, before, after)
        self.assertEqual(external.read_bytes(), canonical(before))

    def test_business_records_and_wrong_binding_identity_are_refused(self):
        from storage_control_projection import publish
        key, before, after = self.records()
        with self.assertRaisesRegex(ValueError, 'category'):
            publish(self.store, self.store.paths.workspace, 'new-operation', 'runs', key, None, after)
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.publish(key, None, {**after, 'id': 'different'})
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.publish(key, None, {**after, 'to': {'workspace': '/different'}})

    def test_replacement_failure_preserves_old_projection_and_can_retry(self):
        key, before, after = self.records()
        path = self.store._path('storage-activations', key)
        self.store._write_path(path, before)
        with patch('storage_control_projection.os.replace', side_effect=OSError('Replace interrupted')):
            with self.assertRaisesRegex(OSError, 'Replace interrupted'):
                self.publish(key, before, after)
        self.assertEqual(path.read_bytes(), canonical(before))
        self.assertFalse(list(path.parent.glob('.control-*')))
        self.publish(key, before, after)
        self.assertEqual(path.read_bytes(), canonical(after))

    def test_changed_history_refuses_even_when_current_projection_matches(self):
        key, before, after = self.records()
        self.store._write_path(self.store._path('storage-activations', key), before)
        result = self.publish(key, before, after)
        history = Path(result['journal_path'])
        history.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'journal'):
            self.publish(key, before, after)
        self.assertEqual(self.store._path('storage-activations', key).read_bytes(), canonical(after))

    def test_successive_changes_preserve_each_transition(self):
        from storage_control_projection import publish
        key, before, after = self.records()
        self.store._write_path(self.store._path('storage-activations', key), before)
        first = self.publish(key, before, after)
        first_bytes = Path(first['journal_path']).read_bytes()
        latest = {**after, 'relocation_id': 'next-operation', 'switch_sha256': 'c' * 64}
        second = publish(self.store, self.store.paths.workspace, 'next-operation',
                         'storage-activations', key, after, latest)
        self.assertNotEqual(first['journal_path'], second['journal_path'])
        self.assertEqual(Path(first['journal_path']).read_bytes(), first_bytes)
        self.assertEqual(self.store._path('storage-activations', key).read_bytes(), canonical(latest))

    def test_restore_previous_projection_keeps_forward_and_rollback_history(self):
        from storage_control_projection import restore
        key, before, after = self.records()
        path = self.store._path('storage-activations', key)
        self.store._write_path(path, before)
        published = self.publish(key, before, after)
        history = Path(published['journal_path']).read_bytes()
        restore(self.store, self.store.paths.workspace, 'new-operation', 'storage-activations', key, before, after)
        restore(self.store, self.store.paths.workspace, 'new-operation', 'storage-activations', key, before, after)
        self.assertEqual(path.read_bytes(), canonical(before))
        self.assertEqual(Path(published['journal_path']).read_bytes(), history)
        self.assertTrue((self.store.paths.workspace / 'records/relocations/new-operation-rollback/control-history/storage-activations' / (key + '.json')).is_file())

    def test_restore_new_projection_removes_only_view_and_keeps_history(self):
        from storage_control_projection import restore
        key, before, after = self.records()
        published = self.publish(key, None, after)
        restore(self.store, self.store.paths.workspace, 'new-operation', 'storage-activations', key, None, after)
        restore(self.store, self.store.paths.workspace, 'new-operation', 'storage-activations', key, None, after)
        self.assertFalse(self.store._path('storage-activations', key).exists())
        self.assertTrue(Path(published['journal_path']).is_file())

    def test_restore_rejects_foreign_projection_edit(self):
        from storage_control_projection import restore
        key, before, after = self.records()
        self.publish(key, None, after)
        path = self.store._path('storage-activations', key)
        modified = {**after, 'switch_sha256': 'c' * 64}
        path.write_bytes(canonical(modified))
        with self.assertRaisesRegex(ValueError, 'rollback evidence'):
            restore(self.store, self.store.paths.workspace, 'new-operation', 'storage-activations', key, None, after)
        self.assertEqual(path.read_bytes(), canonical(modified))
