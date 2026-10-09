"""External publication plans bind committed metadata and approved delivery bytes."""
import json
import shutil
import unittest
import test_publication_lifecycle as fixtures


class ExternalPublicationTests(unittest.TestCase):
    archive_policy = {'schema_version': 1, 'mediaMode': 'external', 'backend': 'team'}
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git

    def persist_external(self):
        saved = self.store.export_external_delivery(self.delivery['id'], 'team', self.root / 'backend')
        shutil.copytree(saved['metadata_path'], self.root / 'bundle')
        self.git('init', '--quiet'); self.git('add', 'bundle')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '--quiet', '-m', 'test: persist external archive')
        return saved, self.git('rev-parse', 'HEAD')

    def plan(self):
        saved, commit = self.persist_external()
        return self.store.plan_external_publication(saved['id'], commit, 'bundle', self.target,
                                                   self.root / 'backend')

    def test_plan_approval_export_and_status_share_external_contract(self):
        plan = self.plan()
        self.assertEqual(plan['retrieval_proof']['media_mode'], 'external')
        self.assertEqual(plan['asset_path_base'], 'hydrated-package')
        self.assertNotIn(str(self.root), json.dumps(plan))
        self.assertFalse((self.root / 'bundle' / plan['assets'][0]['path']).exists())
        approval = self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        self.assertEqual(approval['publication_id'], plan['id'])
        result = self.store.export_publication(plan['id'], write=True)
        self.assertEqual(result['upload_approval'], 'approved')
        status = self.store.publication_status(plan['id'])
        self.assertTrue(status['archive_verified']); self.assertTrue(status['retrieval_verified'])
        self.assertEqual(status['status'], 'UNKNOWN'); self.assertFalse(status['remote_verified'])

    def test_missing_external_version_prevents_plan(self):
        saved, commit = self.persist_external()
        from external_media_store import FileSystemMediaStore
        descriptor = json.loads((self.root / 'bundle/external.json').read_text())
        FileSystemMediaStore('team', self.root / 'backend').object_path(descriptor['objects'][0]['reference']).unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.store.plan_external_publication(saved['id'], commit, 'bundle', self.target, self.root / 'backend')
        self.assertEqual(self.store.list_publications()['publications'], [])

    def test_descriptor_proof_mismatch_refuses_approval_and_status(self):
        plan = self.plan()
        path = self.store._path('publications', plan['id'], 'plan')
        body = json.loads(path.read_text()); body['descriptor_sha256'] = '0' * 64
        path.write_text(json.dumps(body))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        self.assertFalse(self.store.publication_status(plan['id'])['archive_verified'])

    def test_preparation_requires_approval_and_retrieves_actual_asc_files(self):
        plan = self.plan()
        destination = self.root / 'asc-ready'
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.store.prepare_external_publication(plan['id'], self.root / 'backend', destination)
        self.assertFalse(destination.exists())
        self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        result = self.store.prepare_external_publication(plan['id'], self.root / 'backend', destination)
        from artifact_lifecycle import digest
        from pathlib import Path
        for asset in result['assets']:
            self.assertEqual(digest(Path(asset['path'])), asset['sha256'])
        self.assertFalse(result['uploaded']); self.assertFalse(result['remote_write'])
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.store.prepare_external_publication(plan['id'], self.root / 'backend', destination)

    def test_clean_remote_publication_after_original_media_are_removed(self):
        saved, commit = self.persist_external()
        remote = self.root / 'remote.git'
        import subprocess
        subprocess.check_call(['git', 'clone', '--quiet', '--bare', str(self.root), str(remote)])
        self.git('remote', 'add', 'origin', str(remote))
        shutil.rmtree(self.delivery['local_path'])
        shutil.rmtree(saved['metadata_path'])
        shutil.rmtree(self.root / 'bundle')
        shutil.rmtree(self.store.paths.objects)
        plan = self.store.plan_external_publication(saved['id'], commit, 'bundle', self.target,
                                                   self.root / 'backend', 'origin')
        self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        self.assertTrue(self.store.publication_status(plan['id'])['archive_verified'])
        self.assertEqual(self.store.export_publication(plan['id'])['upload_approval'], 'approved')
        destination = self.root / 'clean-consumer'
        prepared = self.store.prepare_external_publication(plan['id'], self.root / 'backend', destination)
        from pathlib import Path
        from artifact_lifecycle import digest
        for asset in prepared['assets']:
            self.assertEqual(digest(Path(asset['path'])), asset['sha256'])
        self.assertEqual(prepared['retrieval_proof']['source_scope'], 'configured-remote')

    def test_public_cli_prepares_verified_paths_from_external_plan(self):
        import subprocess
        import sys
        from pathlib import Path
        saved, commit = self.persist_external()
        self.store.config_path.write_text(json.dumps(self.config))
        target = self.root / 'target.json'; target.write_text(json.dumps(self.target))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        def call(*arguments):
            result = subprocess.run([sys.executable, str(cli), 'publication', *arguments,
                '--repo', str(self.root)], capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        plan = call('plan-external', '--external-archive-id', saved['id'], '--archive-commit', commit,
                    '--archive-path', 'bundle', '--backend-root', str(self.root / 'backend'),
                    '--target', str(target))
        self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        prepared = call('prepare-external', '--id', plan['id'], '--backend-root', str(self.root / 'backend'),
                        '--destination', str(self.root / 'cli-ready'), '--confirm', 'PREPARE')
        self.assertTrue(all(Path(asset['path']).is_file() for asset in prepared['assets']))
        self.assertEqual(prepared['publication_id'], plan['id'])
        self.assertFalse(prepared['remote_write'])

    def test_public_cli_uses_protected_named_backend_without_root_argument(self):
        import subprocess
        import sys
        from pathlib import Path
        saved, commit = self.persist_external()
        self.store.config_path.write_text(json.dumps(self.config))
        (self.root / '.gitignore').write_text('/creative.config.local.json\n')
        local = {'schema_version': 1, 'project_id': self.config['project']['id'], 'storage': {},
                 'mediaBackends': {'team': {'provider': 'filesystem', 'root': str(self.root / 'backend')}}}
        (self.root / 'creative.config.local.json').write_text(json.dumps(local))
        target = self.root / 'target.json'; target.write_text(json.dumps(self.target))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'plan-external', '--repo', str(self.root),
            '--external-archive-id', saved['id'], '--archive-commit', commit, '--archive-path', 'bundle',
            '--target', str(target)], check=True, text=True, capture_output=True)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['backend'], 'team')
        self.assertNotIn(str(self.root / 'backend'), result.stdout)

    def test_preparation_record_survives_restart_and_detects_changed_files(self):
        from artifact_lifecycle import Lifecycle
        from operation_history import verify
        from pathlib import Path
        plan = self.plan()
        self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        prepared = self.store.prepare_external_publication(plan['id'], self.root / 'backend', self.root / 'ready')
        restarted = Lifecycle(self.root, self.config)
        self.assertEqual(restarted.external_preparation_status(prepared['id'])['status'], 'PASS')
        before = restarted._path('publication-preparations', prepared['id']).read_bytes()
        Path(prepared['assets'][0]['path']).write_bytes(b'changed')
        result = restarted.external_preparation_status(prepared['id'])
        self.assertEqual(result['status'], 'FAIL'); self.assertFalse(result['uploaded'])
        self.assertEqual(restarted._path('publication-preparations', prepared['id']).read_bytes(), before)
        self.assertEqual(verify(restarted)['status'], 'PASS')
