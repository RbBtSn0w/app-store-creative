"""A storage change binds both configuration files and updates the owning layer."""
import base64
import json
from pathlib import Path
import unittest
import test_configuration_layers as fixtures


class ConfigurationLayerChangeTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    load = fixtures.ConfigurationLayersTests.load
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def plan(self, storage):
        from configuration_layers import plan_storage_change
        return plan_storage_change(self.load(), storage)

    def verify(self, plan):
        from configuration_layers import verify_storage_change
        return verify_storage_change(self.root, self.path, plan)

    def test_shared_only_change_preserves_recipe_and_does_not_write(self):
        before = self.path.read_bytes()
        plan = self.plan({'workspaceRoot':'next work'})
        target = json.loads(base64.b64decode(plan['target_bytes_base64']))
        self.assertEqual(plan['target_path'], str(self.path))
        self.assertEqual(target['storage'], {'workspaceRoot':'next work'})
        self.assertEqual(target['cards'], self.project['cards'])
        self.assertEqual(plan['source_local_sha256'], None)
        self.assertEqual(base64.b64decode(plan['source_project_bytes_base64']), before)
        self.assertIsNone(plan['source_local_bytes_base64'])
        self.assertEqual(self.verify(plan), plan)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / 'next work').exists())

    def test_local_change_updates_only_local_and_materializes_default_roots(self):
        self.write_local(); before = self.path.read_bytes(); local_before = self.local.read_bytes()
        plan = self.plan({'workspaceRoot':'next host'})
        target = json.loads(base64.b64decode(plan['target_bytes_base64']))
        self.assertEqual(plan['target_path'], str(self.local))
        self.assertEqual(base64.b64decode(plan['source_local_bytes_base64']), local_before)
        self.assertEqual(target['project_id'], 'demo')
        self.assertEqual(target['storage']['releaseRoot'], 'creative-releases')
        self.assertEqual(target['storage']['objectRoot'], 'next host/objects')
        self.assertEqual(plan['target_binding']['releases'], str(self.root / 'creative-releases'))
        self.assertEqual(self.verify(plan), plan)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.local.read_bytes(), local_before)

    def test_either_document_changing_makes_plan_stale(self):
        self.write_local(); plan = self.plan({'workspaceRoot':'next host'})
        self.write_local(storage={'workspaceRoot':'edited host'})
        with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify(plan)
        self.write_local(); plan = self.plan({'workspaceRoot':'next host'})
        self.path.write_text(json.dumps({**self.project, 'cards':[{'id':'new'}]}))
        with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify(plan)

    def test_local_presence_and_absence_are_bound(self):
        plan = self.plan({'workspaceRoot':'next'})
        self.write_local()
        with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify(plan)
        plan = self.plan({'workspaceRoot':'next host'})
        self.local.unlink()
        with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify(plan)

    def test_same_bytes_at_replaced_file_identity_are_not_authorized(self):
        for local in (False, True):
            if local: self.write_local()
            path = self.local if local else self.path
            plan = self.plan({'workspaceRoot':'next'})
            replacement = path.with_name('replacement.json'); replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
            with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify(plan)

    def test_edited_target_or_configuration_path_is_rejected(self):
        self.write_local(); plan = self.plan({'workspaceRoot':'next'})
        for edits in ({'target_path':str(self.root / 'arbitrary.json')}, {'target_bytes_base64':base64.b64encode(b'{}').decode()}, {'project_path':str(self.root / 'other.json')}):
            with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify({**plan, **edits})
        self.assertFalse((self.root / 'arbitrary.json').exists())

    def test_git_protection_is_revalidated_before_accepting_plan(self):
        self.git('init','-q'); self.write_local()
        (self.root / '.gitignore').write_text('/creative.config.local.json\n')
        plan = self.plan({'workspaceRoot':'next'})
        (self.root / '.gitignore').write_text('')
        with self.assertRaisesRegex(ValueError, 'ignored'): self.verify(plan)

    def test_changed_permission_mode_invalidates_plan_without_modifying_bytes(self):
        self.write_local(); self.local.chmod(0o600)
        plan = self.plan({'workspaceRoot':'next'}); before = self.local.read_bytes()
        self.local.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'stale|differs'): self.verify(plan)
        self.assertEqual(self.local.read_bytes(), before)
