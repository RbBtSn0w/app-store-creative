"""Layered runtime data stays private while sealed recipes remain portable."""
import hashlib
import json
from pathlib import Path
import unittest
import test_delivery_lifecycle as fixtures
from artifact_lifecycle import Lifecycle, canonical, verify_archive


class LayeredArchivePortabilityTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp

    def layered_candidate(self):
        config_path = self.root / 'creative.config.json'; config_path.write_text(json.dumps(self.config))
        local = self.root / 'creative.config.local.json'
        self.host_workspace = self.root / 'private host workspace'
        local.write_text(json.dumps({'schema_version':1,'project_id':'demo','storage':{
            'workspaceRoot':str(self.host_workspace),'releaseRoot':str(self.root / 'private host releases')}}))
        core = Lifecycle.from_configuration(self.root, config_path)
        run = core.start_run({'version':'1.5','platform':'MAC_OS'})
        attempt = core.start_attempt(run['id'], 'render', 'operator')
        source = core.register(attempt['id'], self.root / 'source.png', 'source', logical_path='source.png')
        image = core.register(attempt['id'], self.root / 'source.png', 'screenshot', inputs=[source['id']],
                              logical_path='en-US/mac_16_10/hero.png')
        core.finish_attempt(attempt['id'], 'succeeded')
        candidate = core.select(run['id'], [image['id']])
        validation = core.validate_candidate(candidate['id'])
        self.assertEqual(validation['status'], 'PASS')
        approval = core.approve_design(candidate['id'], validation['id'], 'owner', 'human-message:approved')
        delivery = core.seal(candidate['id'], validation['id'], approval['id'])
        return core, run, Path(delivery['local_path'])

    def test_local_run_seals_without_host_paths_or_layer_metadata(self):
        core, run, package = self.layered_candidate()
        self.assertEqual(run['storage']['workspace'], str(self.host_workspace))
        self.assertTrue(run['configuration_layers']['local_document']['present'])
        self.assertTrue(verify_archive(package)['recipe_verified'])
        recipe = json.loads((package / 'recipe/config.json').read_bytes())
        self.assertNotIn('storage', recipe)
        for path in package.rglob('*.json'):
            self.assertNotIn(str(self.host_workspace).encode(), path.read_bytes(), str(path))
            self.assertNotIn(str(core.config_path).encode(), path.read_bytes(), str(path))
            self.assertNotIn(b'configuration_layers', path.read_bytes(), str(path))
        clone = self.root / 'independent package'
        from artifact_lifecycle import restore_archive
        restore_archive(package, clone, verify_archive(package)['manifest_sha256'])
        self.assertTrue(verify_archive(clone)['recipe_verified'])

    def test_matching_file_hashes_do_not_authorize_private_storage_in_portable_recipe(self):
        _, _, package = self.layered_candidate()
        recipe_path = package / 'recipe/config.json'; manifest_path = package / 'manifest.json'
        original_recipe = json.loads(recipe_path.read_bytes()); original_manifest = json.loads(manifest_path.read_bytes())
        for private in ({'storage':{'workspaceRoot':str(self.host_workspace)}},
                        {'configuration_layers':{'local_document':{'path':'/private/local.json'}}},
                        {'project_config_snapshot':{'storage':{'workspaceRoot':'/private/host'}}}):
            with self.subTest(field=next(iter(private))):
                raw = canonical({**original_recipe, **private}); recipe_path.write_bytes(raw)
                manifest = json.loads(json.dumps(original_manifest))
                binding = next(item for item in manifest['files'] if item['path'] == 'recipe/config.json')
                binding['sha256'] = hashlib.sha256(raw).hexdigest(); binding['size_bytes'] = len(raw)
                manifest_path.write_bytes(canonical(manifest))
                with self.assertRaisesRegex(ValueError, 'portable|runtime|storage'):
                    verify_archive(package)
