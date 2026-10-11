"""Internal inode installation follows the recorded owning configuration path."""
import base64
import hashlib
import os
import unittest
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle
from configuration_layers import load, plan_storage_change, owning_document
from configuration_installation import installation_paths, prepare_configuration_installation, verify_configuration_installation


class LocalInstallationTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def journal(self):
        self.write_local(); self.local.chmod(0o600)
        core = Lifecycle.from_configuration(self.root, self.path)
        change = plan_storage_change(load(self.root, self.path), {'workspaceRoot':'next host'})
        authority = owning_document(self.root, self.path, change)
        identity = 'fixture-installation'
        # Unit fixture supplies recorded intent; live preparation is a separate contract.
        prepared = {'id':identity, 'fixture':True}
        with core.transaction():
            core._record('relocations', {'id':identity, 'configuration_change':change,
                         'source_config_file_sha256':hashlib.sha256(authority['source_bytes']).hexdigest()})
            prepared = core._record('relocations', prepared, 'configuration-prepared')
            core._record('relocations', {'id':identity, 'target_config':authority['effective_config'],
                         'source_config_mode':authority['mode'], 'configuration_prepared':prepared,
                         'source_config_base64':base64.b64encode(authority['source_bytes']).decode()}, 'switch-intent')
        return core, identity, authority

    def test_local_installation_and_restoration_preserve_shared_bytes_and_private_mode(self):
        shared = self.path.read_bytes(); core, identity, authority = self.journal()
        target, _, _ = installation_paths(core, identity)
        self.assertEqual(target, self.local)
        temporary = prepare_configuration_installation(core, identity)
        self.assertEqual(temporary.read_bytes(), authority['target_bytes'])
        os.replace(temporary, target)
        verify_configuration_installation(core, identity, installed=True)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        core._record('relocations', {'id':identity, 'source_config_sha256':hashlib.sha256(authority['source_bytes']).hexdigest()}, 'rollback-intent')
        temporary = prepare_configuration_installation(core, identity, restoring=True)
        os.replace(temporary, target)
        verify_configuration_installation(core, identity, installed=True, restoring=True)
        self.assertEqual(target.read_bytes(), authority['source_bytes'])
        self.assertEqual(self.path.read_bytes(), shared)

    def test_same_byte_local_substitution_refuses_installed_proof(self):
        core, identity, _ = self.journal()
        target, _, _ = installation_paths(core, identity)
        os.replace(prepare_configuration_installation(core, identity), target)
        replacement = target.with_name('replacement.json'); replacement.write_bytes(target.read_bytes()); replacement.chmod(0o600)
        replacement.replace(target)
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            verify_configuration_installation(core, identity, installed=True)

    def test_tracked_local_target_refuses_before_installation_staging(self):
        core, identity, _ = self.journal()
        self.git('init', '-q')
        (self.root/'.gitignore').write_text('/creative.config.local.json\n/.creative*\n/.creative.config*\n/host work/\n')
        self.git('add', '-f', 'creative.config.local.json')
        with self.assertRaisesRegex(ValueError, 'tracked'):
            prepare_configuration_installation(core, identity)
        _, temporary, record = installation_paths(core, identity)
        self.assertFalse(temporary.exists()); self.assertFalse(record.exists())
