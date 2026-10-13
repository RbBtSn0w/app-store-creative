"""Forward source copies retain pinned directory and full-tree evidence."""
import json
from pathlib import Path
import shutil
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class ForwardSourceInventoryTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def moved(self):
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Move')
        active = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        return active, plan, artifact

    def test_source_copy_is_verified_and_plan_pins_directory_identity(self):
        active, plan, artifact = self.moved()
        self.assertIn('source_root_identities', plan)
        copies = [copy for copy in active.inventory()['relocation_backups']['copies']
                  if copy['relocation_id'] == plan['id'] and copy['kind'] == 'forward-source']
        self.assertTrue(copies)
        self.assertTrue(all(copy['status'] == 'VERIFIED' for copy in copies))
        self.assertTrue(all(copy['observed_logical_bytes'] is not None for copy in copies))
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_same_bytes_source_root_replacement_invalidates_plan(self):
        artifact = self.source(); self.store.config_path.write_text(json.dumps(self.cfg))
        plan = self.store.plan_relocation(self.targets())
        path = self.store.paths.objects
        retained = path.with_name(path.name + '-old'); path.rename(retained)
        shutil.copytree(retained, path)
        with self.assertRaisesRegex(ValueError, 'source directory identity'):
            self.store.verify_relocation_plan(plan['id'])
        self.assertTrue(retained.is_dir())

    def test_added_source_file_is_reported_without_deletion(self):
        active, plan, artifact = self.moved()
        notes = self.store.paths.workspace / 'owner-notes'; notes.write_text('Keep')
        copy = next(copy for copy in active.inventory()['relocation_backups']['copies']
                    if copy['relocation_id'] == plan['id'] and copy['path'] == str(self.store.paths.workspace))
        self.assertEqual(copy['status'], 'CHANGED')
        self.assertIn('owner-notes', copy['extra_files']); self.assertTrue(notes.exists())

    def test_same_bytes_source_replacement_is_identity_conflict(self):
        active, plan, artifact = self.moved()
        path = self.store.paths.objects
        retained = path.with_name(path.name + '-old'); path.rename(retained); shutil.copytree(retained, path)
        copy = next(copy for copy in active.inventory()['relocation_backups']['copies']
                    if copy['relocation_id'] == plan['id'] and copy['path'] == str(path))
        self.assertEqual(copy['status'], 'IDENTITY_CONFLICT')

    def test_reactivated_source_path_is_not_reported_as_retained_copy(self):
        active, plan, artifact = self.moved()
        reverse = active.plan_reverse_relocation(plan['id'])
        active.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        active.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(active.config_path.read_text()))
        copies = [copy for copy in returned.inventory()['relocation_backups']['copies']
                  if copy['relocation_id'] == plan['id']]
        self.assertTrue(copies)
        self.assertFalse(any(copy['status'] == 'VERIFIED' for copy in copies))
        returned.verify_artifact(artifact['id']); returned.start_run({})

    def test_resume_refuses_tampered_source_manifest_before_activation(self):
        from unittest.mock import patch
        from artifact_lifecycle import canonical
        self.targets = lambda: {**self.cfg['storage'], 'objectRoot': 'new objects'}
        artifact, plan = self.prepared()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Config sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Config sync interrupted'):
                self.store.switch_relocation(plan['id'], 'owner', 'Move')
        path = self.store._path('relocations', plan['id'], 'switch-intent')
        intent = json.loads(path.read_text())
        intent['source_copies'][0]['files'][0]['sha256'] = 'c' * 64
        path.write_bytes(canonical(intent))
        with self.assertRaisesRegex(ValueError, 'source copy evidence'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'switched').exists())

    def test_unreadable_source_tree_refuses_switch_before_fencing(self):
        from unittest.mock import patch
        from inventory_lifecycle import files_without_links
        artifact, plan = self.prepared()
        def read(root, strict=False):
            if Path(root) == self.store.paths.objects:
                if strict:
                    raise PermissionError('Source copy scan denied')
                return [], []
            return files_without_links(root, strict=strict)
        before = self.store.config_path.read_bytes()
        with patch('reverse_relocation.files_without_links', side_effect=read):
            with self.assertRaisesRegex(PermissionError, 'Source copy scan denied'):
                self.store.switch_relocation(plan['id'], 'owner', 'Move')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.store.start_run({})
