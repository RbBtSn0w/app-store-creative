"""LFS archive proof requires objects retrieved from a configured remote."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import test_publication_lifecycle as fixtures
from delivery_lifecycle import verify_git_archive

@unittest.skipUnless(shutil.which('git-lfs'), 'Git LFS required')
class GitLFSRetrievalTests(unittest.TestCase):
    archive_policy = {'schema_version': 1, 'mediaMode': 'lfs'}
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git

    def test_remote_lfs_objects_are_restored_before_archive_verification(self):
        self.git('init', '--quiet')
        self.git('lfs', 'install', '--local', '--skip-smudge', '--skip-repo')
        (self.root / '.gitattributes').write_text('creative-releases/**/*.png filter=lfs diff=lfs merge=lfs -text\n')
        self.git('add', '.gitattributes', 'creative-releases')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','test: LFS archive')
        commit = self.git('rev-parse', 'HEAD')
        with tempfile.TemporaryDirectory() as temporary:
            remote = Path(temporary) / 'remote.git'
            subprocess.run(['git','init','--bare','--quiet',str(remote)],check=True)
            self.git('remote','add','archive',str(remote))
            self.git('-c','core.hooksPath=/dev/null','push','--quiet','archive','HEAD:refs/heads/main')
            self.git('lfs','push','--all','archive',commit)
            subprocess.run(['git','-C',str(remote),'symbolic-ref','HEAD','refs/heads/main'],check=True)
            relative = Path(self.delivery['local_path']).relative_to(self.root).as_posix()
            result = verify_git_archive(self.root,commit,relative,self.delivery['manifest_sha256'],remote='archive')
            self.assertTrue(result['retrieval_verified'])
            self.assertEqual(result['media_mode'],'lfs')
            self.assertEqual(result['source_scope'],'configured-remote')
            plan = self.store.plan_publication(self.delivery['id'],commit,self.target,archive_remote='archive')
            self.assertEqual(plan['retrieval_proof']['media_mode'], 'lfs')
            approval = self.store.approve_upload(plan['id'], 'fixture-owner', 'fixture:upload-approval')
            self.assertEqual(approval['stage'], 'upload')
            exported = self.store.export_publication(plan['id'], write=True)
            self.assertFalse(exported['uploaded'])
            self.assertTrue(self.store.publication_status(plan['id'])['retrieval_verified'])
            with self.assertRaisesRegex(ValueError, 'configured remote'):
                self.store.plan_publication(self.delivery['id'],commit,self.target)


    def persist_lfs(self):
        self.git('init', '--quiet')
        self.git('lfs', 'install', '--local', '--skip-smudge', '--skip-repo')
        (self.root / '.gitattributes').write_text('creative-releases/**/*.png filter=lfs diff=lfs merge=lfs -text\n')
        self.git('add', '.gitattributes', 'creative-releases')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','test: LFS fixture')
        return self.git('rev-parse','HEAD')

    def git_only_remote(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        remote = Path(temporary.name) / 'remote.git'
        subprocess.run(['git','init','--bare','--quiet',str(remote)],check=True)
        self.git('remote','add','archive',str(remote))
        self.git('-c','core.hooksPath=/dev/null','push','--quiet','archive','HEAD:refs/heads/main')
        subprocess.run(['git','-C',str(remote),'symbolic-ref','HEAD','refs/heads/main'],check=True)

    def assert_no_plan(self):
        self.assertEqual(list((self.store.paths.workspace / 'records/publications').glob('*/plan.json')), [])

    def test_missing_remote_objects_cannot_create_a_publication_plan(self):
        commit = self.persist_lfs(); self.git_only_remote()
        with self.assertRaisesRegex(ValueError, 'retrieval failed'):
            self.store.plan_publication(self.delivery['id'],commit,self.target,archive_remote='archive')
        self.assert_no_plan()

    def test_repository_endpoint_override_is_rejected_before_fetch(self):
        self.persist_lfs()
        (self.root / '.lfsconfig').write_text('[lfs]\nurl = https://untrusted.invalid/objects\n')
        self.git('add','.lfsconfig')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','test: endpoint override')
        commit = self.git('rev-parse','HEAD'); self.git_only_remote()
        with self.assertRaisesRegex(ValueError, 'endpoint overrides'):
            self.store.plan_publication(self.delivery['id'],commit,self.target,archive_remote='archive')
        self.assert_no_plan()

    def test_wrong_pointer_hash_cannot_be_used_even_with_valid_working_media(self):
        self.persist_lfs()
        path = Path(self.delivery['local_path']) / 'media/en-US/mac_16_10/hero.png'
        original = path.read_bytes()
        path.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:' + '0'*64 + '\nsize ' + str(len(original)) + '\n')
        self.git('add',str(path.relative_to(self.root)))
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','test: wrong pointer')
        path.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'pointer differs'):
            self.store.plan_publication(self.delivery['id'],self.git('rev-parse','HEAD'),self.target,archive_remote='archive')
        self.assert_no_plan()

    def test_fetch_timeout_is_bounded_sanitized_and_does_not_create_plan(self):
        from unittest.mock import patch
        commit = self.persist_lfs(); self.git_only_remote()
        from delivery_lifecycle import RetrievalCommands
        original = RetrievalCommands.run
        def timeout(instance, arguments, **options):
            if 'lfs' in arguments and 'fetch' in arguments:
                raise ValueError('Independent Git archive retrieval timed out')
            return original(instance, arguments, **options)
        with patch.object(RetrievalCommands, 'run', new=timeout):
            with self.assertRaisesRegex(ValueError, 'retrieval timed out') as failure:
                self.store.plan_publication(self.delivery['id'],commit,self.target,archive_remote='archive')
        self.assertNotIn('fixture-token', str(failure.exception))
        self.assertNotIn('private.invalid', str(failure.exception))
        self.assert_no_plan()
