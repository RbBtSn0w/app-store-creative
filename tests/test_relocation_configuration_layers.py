"""Forward relocation gates pin layered configuration before staging or fencing."""
import base64
import json
from pathlib import Path
import unittest
import test_relocation_switch as fixtures


class RelocationConfigurationLayersTests(unittest.TestCase):
    def setUp(self):
        fixtures.RelocationSwitchTests.setUp(self)
        self.store.config_path.write_text(json.dumps(self.cfg))
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def local(self):
        from configuration_layers import local_path_for
        path = local_path_for(self.store.config_path)
        path.write_text(json.dumps({'schema_version':1, 'project_id':self.cfg['project']['id'], 'storage':{}}))
        return path

    def test_plan_binds_source_documents_and_the_target_update(self):
        self.source(); plan = self.store.plan_relocation(self.targets())
        change = plan['configuration_change']
        self.assertEqual(change['source_local_sha256'], None)
        self.assertEqual(base64.b64decode(change['source_project_bytes_base64']), self.store.config_path.read_bytes())
        self.assertEqual(change['target_binding'], plan['to'])
        self.assertEqual(change['source_binding'], plan['from'])
        self.assertEqual(self.store.verify_relocation_plan(plan['id'])['status'], 'READY')

    def test_new_local_file_invalidates_existing_plan_even_without_overrides(self):
        artifact = self.source(); plan = self.store.plan_relocation(self.targets()); local = self.local()
        with self.assertRaisesRegex(ValueError, 'stale|differs|layer'):
            self.store.verify_relocation_plan(plan['id'])
        self.store.verify_artifact(artifact['id']); self.assertTrue(local.exists())

    def test_prepare_does_not_copy_after_local_configuration_appears(self):
        self.source(); plan = self.store.plan_relocation(self.targets()); self.local()
        with self.assertRaisesRegex(ValueError, 'stale|differs|layer'):
            self.store.prepare_relocation(plan['id'], 'owner', 'Prepare')
        self.assertFalse(self.store._path('relocations', plan['id'], 'prepare-intent').exists())
        self.assertFalse((self.root / self.targets()['workspaceRoot']).exists())

    def test_same_bytes_in_replaced_shared_file_refuse_switch_before_fence(self):
        artifact, plan = self.prepared(); path = self.store.config_path
        replaced = path.with_name('replacement.json'); replaced.write_bytes(path.read_bytes()); replaced.replace(path)
        with self.assertRaisesRegex(ValueError, 'stale|differs|layer'):
            self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertFalse(self.store._path('relocations', plan['id'], 'switch-intent').exists())
        self.store.verify_artifact(artifact['id'])

    def test_layered_preparation_preserves_configuration_until_switch(self):
        self.source(); self.local()
        plan = self.store.plan_relocation(self.targets())
        self.assertEqual(self.store.verify_relocation_plan(plan['id'])['status'], 'READY')
        shared = self.store.config_path.read_bytes()
        self.store.prepare_relocation(plan['id'], 'owner', 'Prepare local plan')
        self.assertEqual(self.store.config_path.read_bytes(), shared)
        self.assertFalse(self.store._path('relocations', plan['id'], 'switch-intent').exists())

    def test_edited_layer_proposal_is_not_used_for_preparation(self):
        self.source(); plan = self.store.plan_relocation(self.targets())
        path = self.store._path('relocations', plan['id'])
        plan['configuration_change']['target_path'] = str(self.root / 'arbitrary.json')
        path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, 'stale|differs|layer'):
            self.store.prepare_relocation(plan['id'], 'owner', 'Prepare')
        self.assertFalse((self.root / 'arbitrary.json').exists())

    def test_planning_without_file_authority_preserves_observed_absence(self):
        self.source(); self.store.config_path.unlink()
        plan = self.store.plan_relocation(self.targets())
        self.assertIsNone(plan['configuration_change'])
        self.assertEqual(self.store.verify_relocation_plan(plan['id'])['status'], 'READY')
        self.store.config_path.write_text(json.dumps(self.cfg))
        with self.assertRaisesRegex(ValueError, 'stale|differs|layer'):
            self.store.verify_relocation_plan(plan['id'])

    def test_local_file_without_shared_authority_refuses_new_plan(self):
        self.source(); self.local(); self.store.config_path.unlink()
        before = sorted((self.store.paths.workspace / 'records/relocations').rglob('*.json'))
        with self.assertRaisesRegex(ValueError, 'shared configuration authority'):
            self.store.plan_relocation(self.targets())
        self.assertEqual(sorted((self.store.paths.workspace / 'records/relocations').rglob('*.json')), before)
