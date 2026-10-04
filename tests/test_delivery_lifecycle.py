"""Release approval, media validation and portable immutable archive contracts."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import subprocess
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import artifact_lifecycle as lifecycle
import studio_contract
from test_v2_workflow import create_mock_png


class DeliveryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {'project': {'id': 'demo', 'name': 'Demo', 'bundleId': 'example.demo', 'locales': ['en-US']},
                       'targets': ['mac_16_10'], 'cards': [{'id': 'hero', 'screenshot': 'source.png'}]}
        self.store = lifecycle.Lifecycle(self.root, self.config)
        self.run = self.store.start_run({'version': '1.5', 'platform': 'MAC_OS'})
        a = self.store.start_attempt(self.run['id'], 'render', 'agent')
        source = self.root / 'source.png'; create_mock_png(source, 2880, 1800)
        self.input = self.store.register(a['id'], source, 'source', logical_path='source.png')
        self.output = self.store.register(a['id'], source, 'screenshot', inputs=[self.input['id']],
                                          logical_path='en-US/mac_16_10/hero.png')
        self.store.finish_attempt(a['id'], 'succeeded')
        self.candidate = self.store.select(self.run['id'], [self.output['id']])

    def approved(self):
        validation = self.store.validate_candidate(self.candidate['id'])
        self.assertEqual(validation['status'], 'PASS', validation.get('errors'))
        approval = self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human-message:approved')
        return validation, approval

    def test_approval_requires_real_media_validation(self):
        self.store.object_path(self.output['sha256']).write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.validate_candidate(self.candidate['id'])

    def test_malformed_media_cannot_be_approved(self):
        run = self.store.start_run({'version': '1.5', 'platform': 'MAC_OS'})
        a = self.store.start_attempt(run['id'], 'render', 'agent')
        path = self.root / 'bad.png'; path.write_bytes(b'not a PNG')
        inp = self.store.register(a['id'], self.root / 'source.png', 'source', logical_path='source.png')
        out = self.store.register(a['id'], path, 'screenshot', inputs=[inp['id']], logical_path='en-US/mac_16_10/hero.png')
        self.store.finish_attempt(a['id'], 'succeeded'); c = self.store.select(run['id'], [out['id']])
        v = self.store.validate_candidate(c['id'])
        self.assertEqual(v['status'], 'FAIL')
        with self.assertRaisesRegex(ValueError, 'validation'):
            self.store.approve_design(c['id'], v['id'], 'owner', 'human-message:approved')

    def test_sealed_package_restores_without_original_workspace(self):
        v, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], v['id'], approval['id'])
        package = Path(delivery['local_path']); clone = self.root / 'independent-clone'
        shutil.copytree(package, clone)
        shutil.rmtree(self.store.paths.workspace)
        result = lifecycle.verify_archive(clone)
        self.assertTrue(result['package_verified'])
        self.assertTrue(result['recipe_verified'])
        self.assertEqual((clone / 'recipe/inputs/source.png').read_bytes(), (self.root / 'source.png').read_bytes())
        self.assertNotIn(str(self.root), (clone / 'manifest.json').read_text())
        restored_config = json.loads((clone / 'recipe/config.json').read_text())
        sources, errors = studio_contract.input_hashes(clone / 'recipe', restored_config)
        self.assertEqual(errors, [], 'Portable recipe must actually resolve its source captures')
        self.assertIn('inputs/source.png', sources)

    def test_archive_corruption_is_not_success(self):
        v, approval = self.approved(); d = self.store.seal(self.candidate['id'], v['id'], approval['id'])
        package = Path(d['local_path']); target = package / 'media/en-US/mac_16_10/hero.png'
        target.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            lifecycle.verify_archive(package)

    def test_archive_cli_can_verify_without_project_configuration(self):
        v, approval = self.approved(); d = self.store.seal(self.candidate['id'], v['id'], approval['id'])
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        isolated = self.root / 'fresh'; isolated.mkdir()
        process = subprocess.run([sys.executable, str(cli), 'archive', '--repo', str(isolated),
                                  'verify', '--path', d['local_path'], '--expected-sha256', d['manifest_sha256']],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(json.loads(process.stdout)['recipe_verified'])

    def test_undeclared_outputs_cannot_enter_an_approved_release(self):
        a = self.store.start_attempt(self.run['id'], 'render', 'agent')
        extra = self.store.register(a['id'], self.root / 'source.png', 'screenshot', inputs=[self.input['id']],
                                    logical_path='en-US/mac_16_10/not-declared.png')
        self.store.finish_attempt(a['id'], 'succeeded')
        c = self.store.select(self.run['id'], [self.output['id'], extra['id']])
        result = self.store.validate_candidate(c['id'])
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(any('declared' in finding for finding in result['errors']))

    def test_restore_copies_and_verifies_without_overwriting_user_files(self):
        v, approval = self.approved(); d = self.store.seal(self.candidate['id'], v['id'], approval['id'])
        destination = self.root / 'restored'
        result = lifecycle.restore_archive(d['local_path'], destination, d['manifest_sha256'])
        self.assertTrue(result['recipe_verified'])
        (destination / 'user.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'exists'):
            lifecycle.restore_archive(d['local_path'], destination, d['manifest_sha256'])
        self.assertEqual((destination / 'user.txt').read_text(), 'keep')

    def test_changed_config_invalidates_design_scope(self):
        v, approval = self.approved()
        self.store.config['cards'][0]['headline'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'configuration'):
            self.store.seal(self.candidate['id'], v['id'], approval['id'])

    def test_approval_requires_explicit_actor_and_authorization_reference(self):
        v = self.store.validate_candidate(self.candidate['id'])
        with self.assertRaisesRegex(ValueError, 'authorization'):
            self.store.approve_design(self.candidate['id'], v['id'], '', '')

    def test_each_seal_creates_a_new_revision_without_overwriting(self):
        v, approval = self.approved(); d = self.store.seal(self.candidate['id'], v['id'], approval['id'])
        snapshot = (Path(d['local_path']) / 'manifest.json').read_bytes()
        second = self.store.seal(self.candidate['id'], v['id'], approval['id'], parent_revision=d['id'])
        self.assertNotEqual(d['id'], second['id'])
        self.assertEqual((Path(d['local_path']) / 'manifest.json').read_bytes(), snapshot)
        self.assertEqual(second['parent_revision'], d['id'])

if __name__ == '__main__':
    unittest.main()
