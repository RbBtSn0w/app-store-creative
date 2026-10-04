"""Publication plans must bind persisted Git archives and explicit upload scope."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import artifact_lifecycle as lifecycle
import test_delivery_lifecycle as fixtures


class PublicationLifecycleTests(unittest.TestCase):
    def setUp(self):
        fixtures.DeliveryLifecycleTests.setUp(self)
        validation = self.store.validate_candidate(self.candidate['id'])
        approval = self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human:design')
        self.delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.target = {'app_id': '123456', 'version_id': 'version-resource', 'platform': 'MAC_OS'}

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def persist(self):
        self.git('init', '--quiet')
        self.git('add', 'creative-releases')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--quiet', '-m', 'test: persist archive')
        return self.git('rev-parse', 'HEAD')

    def test_plan_binds_actual_committed_archive_and_exact_bytes(self):
        sha = self.persist()
        plan = self.store.plan_publication(self.delivery['id'], sha, self.target)
        self.assertEqual(plan['archive_commit'], sha)
        self.assertEqual(plan['manifest_sha256'], self.delivery['manifest_sha256'])
        self.assertFalse(plan['remote_write'])
        self.assertEqual(plan['assets'][0]['source_checksum'], hashlib.md5((self.root / 'source.png').read_bytes()).hexdigest())
        approval = self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        self.assertEqual(approval['stage'], 'upload')
        self.assertEqual(approval['publication_id'], plan['id'])

    def test_plan_cannot_use_uncommitted_archive(self):
        self.git('init', '--quiet')
        with self.assertRaisesRegex(ValueError, 'commit|archive'):
            self.store.plan_publication(self.delivery['id'], '0'*40, self.target)

    def test_foreign_target_platform_is_rejected(self):
        sha = self.persist()
        with self.assertRaisesRegex(ValueError, 'platform'):
            self.store.plan_publication(self.delivery['id'], sha, {**self.target, 'platform': 'IOS'})

    def test_exported_handoff_keeps_upload_approval_separate(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        result = self.store.export_publication(plan['id'], write=True)
        self.assertFalse(result['uploaded'])
        self.assertFalse(result['remote_write'])
        self.assertEqual(result['upload_approval'], 'pending')
        exported = Path(result['handoff_path'])
        self.assertEqual(json.loads(exported.read_text())['id'], plan['id'])
        self.assertNotIn(str(self.root), exported.read_text())
        self.assertEqual(self.store.export_publication(plan['id'], write=True)['handoff_path'], str(exported))

    def test_unknown_remote_state_never_counts_as_complete(self):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        state = self.store.publication_status(plan['id'])
        self.assertEqual(state['status'], 'UNKNOWN')
        self.assertFalse(state['remote_verified'])

    def test_corrupted_working_archive_does_not_bypass_commit_binding(self):
        sha = self.persist()
        path = Path(self.delivery['local_path']) / 'media/en-US/mac_16_10/hero.png'
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.plan_publication(self.delivery['id'], sha, self.target)

if __name__ == '__main__':
    unittest.main()
