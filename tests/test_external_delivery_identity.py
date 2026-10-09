"""External plans compare delivery identity against the committed archive manifest."""
import json
import unittest
import test_external_publication as fixtures


class ExternalDeliveryIdentityTests(unittest.TestCase):
    setUp = fixtures.ExternalPublicationTests.setUp
    git = fixtures.ExternalPublicationTests.git
    persist_external = fixtures.ExternalPublicationTests.persist_external
    plan = fixtures.ExternalPublicationTests.plan

    def test_changed_delivery_target_cannot_relabel_external_archive(self):
        saved, commit = self.persist_external()
        path = self.store._path('deliveries', self.delivery['id'])
        delivery = json.loads(path.read_bytes()); delivery['target']['platform'] = 'IOS'
        path.write_text(json.dumps(delivery))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.plan_external_publication(saved['id'], commit, 'bundle',
                {**self.target, 'platform': 'IOS'}, self.root / 'backend')
        self.assertEqual(self.store.list_publications()['publications'], [])

    def test_changed_delivery_project_cannot_authorize_external_publication(self):
        plan = self.plan()
        path = self.store._path('deliveries', self.delivery['id'])
        delivery = json.loads(path.read_bytes()); delivery['project_id'] = 'foreign-project'
        path.write_text(json.dumps(delivery))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload')
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.export_publication(plan['id'], write=True)
        self.assertFalse((self.store.paths.publications / plan['id'] / 'plan.json').exists())

    def test_changed_external_assets_cannot_authorize_handoff(self):
        plan = self.plan()
        path = self.store._path('publications', plan['id'], 'plan')
        for change in ({'path': '../outside.png'}, {'sha256': '0' * 64},
                       {'role': 'preview'}, {'artifact_id': 'other'}):
            with self.subTest(change=change):
                changed = json.loads(json.dumps(plan))
                changed['assets'][0].update(change)
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload')
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.export_publication(plan['id'], write=True)
                self.assertFalse((self.store.paths.publications / plan['id'] / 'plan.json').exists())

    def test_wrong_checksum_cannot_create_external_preparation(self):
        plan = self.plan()
        from artifact_lifecycle import identifier
        changed = json.loads(json.dumps(plan))
        changed['id'] = identifier()
        changed['assets'][0]['source_checksum'] = '0' * 32
        # A newly committed fixture isolates checksum validation from tamper rejection.
        with self.store.transaction():
            plan = self.store._record('publications', changed, 'plan')
        self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload')
        destination = self.root / 'checksum-preparation'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store.prepare_external_publication(plan['id'], self.root / 'backend', destination)
        self.assertEqual(list((self.store.paths.workspace / 'records/publication-preparations').glob('*.json')), [])
        # Keep successfully retrieved bytes for diagnosis; no automatic deletion.
        self.assertTrue(destination.exists())

    def test_checksum_validation_streams_media_larger_than_configuration_limit(self):
        import hashlib
        package = self.root / 'large-media'
        package.mkdir()
        path = package / 'preview.mp4'
        sha = hashlib.sha256()
        checksum = hashlib.md5()
        chunk = b'large-media-fixture' * 65536
        with path.open('wb') as stream:
            for _ in range(27):
                stream.write(chunk)
                sha.update(chunk)
                checksum.update(chunk)
        self.assertGreater(path.stat().st_size, 30 * 1024 * 1024)
        plan = {'assets': [{'path': path.name, 'sha256': sha.hexdigest(),
                            'source_checksum': checksum.hexdigest()}]}
        self.store._check_prepared_checksums(plan, package)
        with path.open('r+b') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.store._check_prepared_checksums(plan, package)

    def test_preparation_status_rechecks_actual_checksum(self):
        import hashlib
        from artifact_lifecycle import canonical
        plan = self.plan()
        self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload')
        prepared = self.store.prepare_external_publication(plan['id'], self.root / 'backend', self.root / 'ready')
        self.assertTrue(self.store.external_preparation_status(prepared['id'])['files_verified'])
        changed = json.loads(json.dumps(plan))
        changed['assets'][0]['source_checksum'] = '0' * 32
        self.store._path('publications', plan['id'], 'plan').write_text(json.dumps(changed))
        saved = json.loads(json.dumps(prepared))
        saved['plan_sha256'] = hashlib.sha256(canonical(changed)).hexdigest()
        saved['assets'][0]['source_checksum'] = '0' * 32
        self.store._path('publication-preparations', prepared['id']).write_text(json.dumps(saved))
        result = self.store.external_preparation_status(prepared['id'])
        self.assertEqual(result['status'], 'FAIL')
        self.assertIsNone(result['publication_id'])
        self.assertFalse(result['files_verified'])
        self.assertFalse(result['remote_verified'])

    def test_checksum_validation_refuses_fifo_before_opening_media(self):
        import os
        if not hasattr(os, 'mkfifo'):
            self.skipTest('Requires POSIX named pipes')
        package = self.root / 'fifo-media'
        package.mkdir()
        path = package / 'preview.mp4'
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.store._check_prepared_checksums({'assets': [{'path': path.name,
                'sha256': '0' * 64, 'source_checksum': '0' * 32}]}, package)
        self.assertTrue(path.exists())
