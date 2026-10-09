"""Configuration installation authority identifies the actual owning document."""
import copy
import unittest
import test_configuration_layers as fixtures
from configuration_layers import load, plan_storage_change


class OwningDocumentTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local

    def authority(self, plan):
        from configuration_layers import owning_document
        return owning_document(self.root, self.path, plan)

    def test_shared_and_local_owner_bind_exact_source_target_and_mode(self):
        for local in (False, True):
            if local: self.write_local(); self.local.chmod(0o600)
            layers = load(self.root, self.path)
            plan = plan_storage_change(layers, {'workspaceRoot':'next work'})
            authority = self.authority(plan)
            owner = self.local if local else self.path
            self.assertEqual(authority['path'], owner)
            self.assertEqual(authority['source_bytes'], owner.read_bytes())
            self.assertEqual(authority['mode'], owner.stat().st_mode & 0o777)
            self.assertEqual(authority['effective_config']['storage']['workspaceRoot'], 'next work')
            self.assertEqual(authority['source_identity'], plan['source_local_identity'] if local else plan['source_project_identity'])

    def test_inconsistent_snapshot_and_arbitrary_target_are_refused_without_writes(self):
        self.write_local(); plan = plan_storage_change(load(self.root, self.path), {'workspaceRoot':'next work'})
        before = self.path.read_bytes(), self.local.read_bytes()
        for key, value in [('target_path','/private/other.json'), ('source_project_sha256','0'*64),
                           ('target_sha256','0'*64), ('source_revision','0'*64)]:
            changed = copy.deepcopy(plan); changed[key] = value
            with self.assertRaises(ValueError): self.authority(changed)
        self.assertEqual((self.path.read_bytes(), self.local.read_bytes()), before)
        self.assertFalse((self.root/'next work').exists())
