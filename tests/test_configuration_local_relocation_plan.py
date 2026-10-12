"""Forward relocation planning binds the local owning document without activation."""
import hashlib
import unittest
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle


class LocalRelocationPlanTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def test_layered_plan_records_local_backup_hash_and_verifies_without_activation(self):
        self.write_local(); core = Lifecycle.from_configuration(self.root, self.path)
        before = self.path.read_bytes(), self.local.read_bytes()
        plan = core.plan_relocation({'workspaceRoot':'next host'})
        self.assertEqual(plan['configuration_change']['target_path'], str(self.local))
        self.assertEqual(plan['source_config_file_sha256'], hashlib.sha256(before[1]).hexdigest())
        self.assertEqual(core.verify_relocation_plan(plan['id'])['status'], 'READY')
        core.prepare_relocation(plan['id'], 'fixture', 'Prepare verified local plan')
        self.assertEqual((self.path.read_bytes(), self.local.read_bytes()), before)
        self.assertFalse((self.root/'next host').exists())

    def test_git_policy_names_local_owner_and_exact_installation_paths_without_writes(self):
        self.git('init', '-q'); self.write_local()
        rules = self.root/'.gitignore'; rules.write_text('/creative.config.local.json\n/host work/\n')
        core = Lifecycle.from_configuration(self.root, self.path)
        plan = core.plan_relocation({'workspaceRoot':'next host'})
        before = {str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        policy = core.relocation_git_policy(plan['id'])
        self.assertEqual(policy['configuration_target'], str(self.local))
        self.assertEqual(policy['configuration_layer'], 'local')
        self.assertIn('/creative.config.local.json', policy['gitignore'])
        self.assertIn('creative.config.local.json.creative-install-', policy['configuration_installation_staging'])
        self.assertIn('creative.config.local.json.creative-rollback-install-', policy['configuration_restoration_staging'])
        self.assertEqual({str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)
