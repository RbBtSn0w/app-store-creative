"""Host-local storage precedence and actual Git protection are explicit."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
from artifact_lifecycle import configuration_identity


class ConfigurationLayersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'creative.config.json'
        self.project = {'project': {'id':'demo'}, 'cards':[], 'storage':{'workspaceRoot':'shared work', 'releaseRoot':'shared releases'}}
        self.path.write_text(json.dumps(self.project))
        self.local = self.root / 'creative.config.local.json'

    def load(self):
        from configuration_layers import load
        return load(self.root, self.path)

    def write_local(self, **changes):
        self.local.write_text(json.dumps({'schema_version':1, 'project_id':'demo', 'storage':{'workspaceRoot':'host work'}, **changes}))

    def git(self, *arguments):
        return subprocess.run(['git','-C',str(self.root),*arguments],check=True,capture_output=True,text=True)

    def test_no_local_file_preserves_shared_config_and_reports_sources(self):
        result = self.load()
        self.assertEqual(result.config, self.project)
        self.assertEqual(result.paths.objects, self.root / 'shared work/objects')
        self.assertEqual(result.sources['workspaceRoot'], 'project')
        self.assertEqual(result.sources['objectRoot'], 'derived')
        self.assertEqual(result.sources['publicationRoot'], 'default')
        self.assertIsNone(result.local_sha256)
        self.assertFalse(self.local.exists())

    def test_local_storage_wins_without_changing_recipe_or_project_file(self):
        self.write_local()
        before = self.path.read_bytes()
        result = self.load()
        self.assertEqual(result.paths.workspace, self.root / 'host work')
        self.assertEqual(result.paths.objects, self.root / 'host work/objects')
        self.assertEqual(result.paths.releases, self.root / 'shared releases')
        self.assertEqual(result.sources['workspaceRoot'], 'local')
        self.assertEqual(configuration_identity(result.config), configuration_identity(self.project))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(result.paths.workspace.exists())
        self.assertIsNotNone(result.local_sha256)

    def test_local_identity_recipe_fields_and_unknown_roots_are_rejected(self):
        for changes in ({'project_id':'other'}, {'schema_version':True}, {'cards':[]}, {'storage':{'unknownRoot':'x'}}, {'storage':{'workspaceRoot':None}}):
            self.write_local(**changes)
            with self.assertRaises(ValueError): self.load()
        self.assertFalse((self.root / 'host work').exists())

    def test_symbolic_local_configuration_is_not_read(self):
        outside = self.root / 'external.json'; outside.write_text('private bytes')
        self.local.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'regular|symlink|unsafe'): self.load()
        self.assertEqual(outside.read_text(), 'private bytes')

    def test_real_git_requires_ignored_and_untracked_local_configuration(self):
        self.git('init','-q'); self.write_local()
        with self.assertRaisesRegex(ValueError, 'ignored'): self.load()
        (self.root / '.gitignore').write_text('/creative.config.local.json\n')
        self.assertEqual(self.load().sources['workspaceRoot'], 'local')
        self.git('add','-f','creative.config.local.json')
        with self.assertRaisesRegex(ValueError, 'tracked'): self.load()
        self.assertTrue(self.git('ls-files','--','creative.config.local.json').stdout)

    def test_negated_ignore_rule_is_not_accepted(self):
        self.git('init','-q'); self.write_local()
        (self.root / '.gitignore').write_text('*.local.json\n!creative.config.local.json\n')
        with self.assertRaisesRegex(ValueError, 'ignored'): self.load()

    def test_two_documents_and_absence_have_distinct_revisions(self):
        first = self.load().revision
        self.write_local(); second = self.load().revision
        self.assertNotEqual(first, second)
        self.write_local(storage={'workspaceRoot':'next host'})
        self.assertNotEqual(self.load().revision, second)
        self.local.unlink()
        self.assertEqual(self.load().revision, first)

    def test_effective_path_conflicts_and_relative_escapes_are_rejected(self):
        for storage in ({'workspaceRoot':'shared releases/work'}, {'workspaceRoot':'../escape'}, {'objectRoot':'/'}):
            self.write_local(storage=storage)
            with self.assertRaises(ValueError): self.load()

    def test_duplicate_keys_are_not_accepted_as_override_authority(self):
        self.local.write_text('{"schema_version":1,"project_id":"demo","project_id":"other","storage":{}}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): self.load()

    def test_local_file_is_derived_from_the_selected_project_config(self):
        self.path = self.root / 'review [draft].json'
        self.path.write_text(json.dumps(self.project))
        self.local = self.root / 'review [draft].local.json'
        self.write_local(); result = self.load()
        self.assertEqual(result.local_path, self.local)
        self.assertEqual(result.sources['workspaceRoot'], 'local')
        self.assertEqual(result.paths.workspace, self.root / 'host work')

    def test_layer_change_during_resolution_is_rejected_and_preserved(self):
        from unittest.mock import patch
        import configuration_layers
        self.write_local()
        original = configuration_layers._read_regular
        reads = 0
        def read(path, optional=False):
            nonlocal reads
            value = original(path, optional)
            if path == self.local:
                reads += 1
                if reads == 1:
                    self.write_local(storage={'workspaceRoot':'changed host'})
            return value
        with patch('configuration_layers._read_regular', side_effect=read):
            with self.assertRaisesRegex(ValueError, 'layers changed'): self.load()
        self.assertEqual(json.loads(self.local.read_text())['storage']['workspaceRoot'], 'changed host')
        self.assertFalse((self.root / 'host work').exists())

    def test_named_backend_stays_local_and_survives_storage_relocation_plan(self):
        backend = {'team': {'provider': 'filesystem', 'root': str(self.root / 'external')}}
        self.write_local(mediaBackends=backend)
        layers = self.load()
        self.assertNotIn('mediaBackends', layers.config)
        self.assertEqual(configuration_identity(layers.config), configuration_identity(self.project))
        from configuration_layers import plan_storage_change
        plan = plan_storage_change(layers, {'workspaceRoot': 'next-work', 'releaseRoot': 'next-release',
                                           'publicationRoot': 'next-publication'})
        import base64
        target = json.loads(base64.b64decode(plan['target_bytes_base64']))
        self.assertEqual(target['mediaBackends'], backend)

    def test_invalid_backend_access_configuration_is_rejected(self):
        for backend in ({'team': {'provider': 'filesystem', 'root': 'relative'}},
                        {'team': {'provider': 'cloud', 'root': '/external'}},
                        {'team': {'provider': 'filesystem', 'root': '/external', 'token': 'secret'}},
                        {'../team': {'provider': 'filesystem', 'root': '/external'}}):
            self.write_local(mediaBackends=backend)
            with self.assertRaisesRegex(ValueError, 'backend'):
                self.load()
