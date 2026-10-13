"""Public lifecycle commands consume protected layered configuration."""
import argparse
import json
import unittest
import test_configuration_layers as fixtures
from lifecycle_commands import execute


class ConfigurationCommandTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def args(self, command, action, **values):
        return argparse.Namespace(repo=self.root, config=self.path, command=command, action=action, **values)

    def test_inspect_and_run_use_local_roots_without_rewriting_documents(self):
        self.write_local()
        original = self.path.read_bytes(), self.local.read_bytes()
        binding = execute(self.args('storage', 'inspect'))
        self.assertEqual(binding['workspace'], str(self.root / 'host work'))
        target = self.root / 'target.json'; target.write_text('{}')
        run = execute(self.args('run', 'start', target=target))
        self.assertEqual(run['configuration_layers']['sources']['workspaceRoot'], 'local')
        self.assertEqual(run['project_config_snapshot'], self.project)
        self.assertFalse((self.root / 'shared work').exists())
        self.assertEqual((self.path.read_bytes(), self.local.read_bytes()), original)

    def test_unprotected_git_local_override_refuses_before_workspace_creation(self):
        self.git('init', '-q'); self.write_local()
        with self.assertRaisesRegex(ValueError, 'ignored'):
            execute(self.args('storage', 'inspect'))
        self.assertFalse((self.root / 'host work').exists())
        self.assertFalse((self.root / 'shared work').exists())
