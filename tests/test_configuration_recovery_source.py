"""Recovery reconstructs effective source config from recorded owning layers."""
import base64
import hashlib
import json
import unittest
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle, canonical
from configuration_layers import load, plan_storage_change
from relocation_lifecycle import recovery_source


class LayeredRecoverySourceTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local

    def journal(self, local=True):
        if local: self.write_local()
        layers = load(self.root, self.path)
        source_bytes = layers.local_bytes if local else layers.project_bytes
        core = Lifecycle.from_configuration(self.root, self.path); identity='fixture-recovery'
        change = plan_storage_change(layers, {'workspaceRoot':'next host'})
        with core.transaction():
            core._record('relocations', {'id':identity, 'operation':'relocation-plan',
                'configuration_change':change, 'config_path':str(self.path), 'from':core.paths.binding(),
                'source_config_file_sha256':hashlib.sha256(source_bytes).hexdigest(),
                'source_config_sha256':hashlib.sha256(canonical(layers.config)).hexdigest()})
            core._record('relocations', {'id':identity,
                'source_config_base64':base64.b64encode(source_bytes).decode()}, 'switch-intent')
        return core, identity, layers

    def test_local_owner_backup_is_not_misread_as_full_project_recipe(self):
        core, identity, layers = self.journal()
        before = {str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        recovered = recovery_source(self.root, self.path, core.paths.workspace, identity)
        self.assertEqual(recovered.config, layers.config)
        self.assertEqual(recovered.config['project'], self.project['project'])
        self.assertEqual(recovered.paths.binding(), core.paths.binding())
        self.assertEqual({str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

    def test_duplicate_recovery_authority_keys_are_refused_without_writes(self):
        core, identity, _ = self.journal()
        authority = core.paths.workspace/'configuration-authority.json'
        value = json.dumps(str(self.path))
        authority.write_text('{"config_path":' + value + ',"config_path":' + value + '}')
        before = {str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            recovery_source(self.root, self.path, core.paths.workspace, identity)
        self.assertEqual({str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

    def test_rehashed_backup_cannot_replace_recorded_owning_source(self):
        core, identity, _ = self.journal()
        plan_path = core._path('relocations', identity)
        intent_path = core._path('relocations', identity, 'switch-intent')
        plan = json.loads(plan_path.read_text()); intent = json.loads(intent_path.read_text())
        substituted = b'{"schema_version":1,"project_id":"demo","storage":{"workspaceRoot":"other"}}'
        plan['source_config_file_sha256'] = hashlib.sha256(substituted).hexdigest()
        intent['source_config_base64'] = base64.b64encode(substituted).decode()
        plan_path.write_text(json.dumps(plan)); intent_path.write_text(json.dumps(intent))
        before = {str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with self.assertRaisesRegex(ValueError, 'owning.*differs'):
            recovery_source(self.root, self.path, core.paths.workspace, identity)
        self.assertEqual({str(path):path.read_bytes() for path in self.root.rglob('*') if path.is_file()}, before)

    def test_missing_new_layer_authority_is_refused_instead_of_legacy_fallback(self):
        core, identity, _ = self.journal(local=False)
        path = core._path('relocations', identity)
        plan = json.loads(path.read_text()); plan.pop('configuration_change')
        path.write_text(json.dumps(plan))
        before = {str(item):item.read_bytes() for item in self.root.rglob('*') if item.is_file()}
        with self.assertRaisesRegex(ValueError, 'configuration.*authority|layer.*required'):
            recovery_source(self.root, self.path, core.paths.workspace, identity)
        self.assertEqual({str(item):item.read_bytes() for item in self.root.rglob('*') if item.is_file()}, before)
