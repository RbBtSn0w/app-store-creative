"""The canonical configuration factory binds runtime reads to both documents."""
import json
from pathlib import Path
import unittest
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle


class ConfigurationRuntimeTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def core(self):
        return Lifecycle.from_configuration(self.root, self.path)

    def test_factory_uses_local_storage_and_records_recipe_and_layer_provenance(self):
        self.write_local(); before = self.path.read_bytes(), self.local.read_bytes()
        core = self.core(); run = core.start_run({})
        self.assertEqual(core.paths.workspace, self.root / 'host work')
        self.assertFalse((self.root / 'shared work').exists())
        self.assertEqual(run['project_config_snapshot'], self.project)
        self.assertEqual(run['config']['storage']['workspaceRoot'], 'host work')
        self.assertEqual(run['configuration_layers']['sources']['workspaceRoot'], 'local')
        self.assertTrue(run['configuration_layers']['local_document']['present'])
        self.assertEqual((self.path.read_bytes(), self.local.read_bytes()), before)
        attempt = core.start_attempt(run['id'], 'render', 'operator')
        payload = core.work_path(attempt['id']) / 'source'; payload.write_bytes(b'local runtime media')
        artifact = core.register(attempt['id'], payload, 'source')
        core.finish_attempt(attempt['id'], 'failed', reason='Unused fixture')
        core.verify_artifact(artifact['id'])
        self.assertEqual(self.core()._run(run['id']), run)

    def test_shared_only_factory_binds_local_absence(self):
        core = self.core(); run = core.start_run({})
        self.assertEqual(run['configuration_layers']['sources']['workspaceRoot'], 'project')
        self.assertFalse(run['configuration_layers']['local_document']['present'])
        self.assertEqual(run['configuration_layers']['project_document']['sha256'], run['configuration_layers']['revision'])
        self.assertEqual(run['config'], self.project)

    def test_changed_either_document_refuses_stale_runtime_without_creating_workspace(self):
        self.write_local(); core = self.core()
        self.local.write_text(json.dumps({'schema_version':1,'project_id':'demo','storage':{'workspaceRoot':'edited host'}}))
        with self.assertRaisesRegex(ValueError, 'layers.*changed|stale'): core.start_run({})
        self.assertFalse(core.paths.workspace.exists())
        self.write_local(); core = self.core()
        self.path.write_text(json.dumps({**self.project,'cards':[{'id':'edited'}]}))
        with self.assertRaisesRegex(ValueError, 'layers.*changed|stale'): core.start_run({})
        self.assertFalse(core.paths.workspace.exists())

    def test_same_bytes_replacement_and_local_appearance_are_not_authorized(self):
        core = self.core(); before = self.path.read_bytes()
        replacement = self.root / 'replacement'; replacement.write_bytes(before); replacement.replace(self.path)
        with self.assertRaisesRegex(ValueError, 'layers.*changed|stale'): core.start_run({})
        core = self.core(); self.write_local(storage={})
        with self.assertRaisesRegex(ValueError, 'layers.*changed|stale'): core.start_run({})
        self.assertFalse(core.paths.workspace.exists())

    def test_git_protection_is_checked_again_before_runtime_write(self):
        self.git('init','-q'); self.write_local()
        rules = self.root / '.gitignore'; rules.write_text('/creative.config.local.json\n/host work/\n')
        core = self.core(); rules.write_text('')
        with self.assertRaisesRegex(ValueError, 'ignored'): core.start_run({})
        self.assertFalse(core.paths.workspace.exists())

    def test_mutated_effective_snapshot_is_not_recorded_as_authoritative_input(self):
        self.write_local(); core = self.core(); core.config['cards'] = [{'id':'injected'}]
        with self.assertRaisesRegex(ValueError, 'snapshot|layers.*changed'): core.start_run({})
        self.assertFalse(core.paths.workspace.exists())

    def test_historical_run_stays_bound_after_new_local_workspace_is_selected(self):
        self.write_local(); original = self.core(); run = original.start_run({})
        self.write_local(storage={'workspaceRoot':'next host'})
        current = self.core(); next_run = current.start_run({})
        self.assertNotEqual(run['storage'], next_run['storage'])
        self.assertEqual(original._read('runs', run['id'])['storage'], run['storage'])
        with self.assertRaisesRegex(ValueError, 'layers.*changed|stale'): original.start_run({})

    def test_run_uses_fresh_authoritative_shared_snapshot_not_mutated_cached_document(self):
        self.write_local(); core = self.core()
        core._configuration_layers.project_config['cards'] = [{'id':'cached mutation'}]
        run = core.start_run({})
        self.assertEqual(run['project_config_snapshot'], self.project)
        self.assertEqual(run['config']['cards'], self.project['cards'])
