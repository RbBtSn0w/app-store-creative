"""Metadata-only copies restore complete approved archives from stable objects."""
import shutil
import unittest
import test_delivery_lifecycle as fixtures
from delivery_lifecycle import verify_archive
from external_delivery_archive import externalize, restore_external


class ExternalDeliveryArchiveTests(unittest.TestCase):
    archive_policy = {'schema_version': 1, 'mediaMode': 'external', 'backend': 'team'}
    setUp=fixtures.DeliveryLifecycleTests.setUp
    approved=fixtures.DeliveryLifecycleTests.approved

    def bundle(self):
        validation,approval=self.approved()
        delivery=self.store.seal(self.candidate['id'],validation['id'],approval['id'])
        result=externalize(delivery['local_path'],self.root/'metadata','team',self.root/'backend',delivery['manifest_sha256'])
        return delivery,result

    def test_metadata_only_copy_restores_without_original_archive_or_workspace(self):
        delivery,result=self.bundle()
        clone=self.root/'clean-copy';shutil.copytree(self.root/'metadata',clone)
        shutil.rmtree(delivery['local_path']);shutil.rmtree(self.store.paths.workspace)
        restored=restore_external(clone,self.root/'restored','team',self.root/'backend',result['descriptor_sha256'])
        self.assertTrue(restored['package_verified'])
        self.assertEqual(verify_archive(self.root/'restored')['manifest_sha256'],delivery['manifest_sha256'])
        self.assertFalse((clone/'archive/media').exists())
        self.assertNotIn(str(self.root),(clone/'external.json').read_text())

    def test_wrong_descriptor_hash_is_rejected_before_restore(self):
        _,result=self.bundle()
        with self.assertRaisesRegex(ValueError,'descriptor'):
            restore_external(self.root/'metadata',self.root/'restored','team',self.root/'backend','0'*64)
        self.assertFalse((self.root/'restored').exists())

    def test_missing_external_object_does_not_publish_partial_archive(self):
        _,result=self.bundle()
        from external_media_store import FileSystemMediaStore
        import json
        descriptor=json.loads((self.root/'metadata/external.json').read_text())
        reference=descriptor['objects'][0]['reference']
        FileSystemMediaStore('team',self.root/'backend').object_path(reference).unlink()
        with self.assertRaisesRegex(ValueError,'missing'):
            restore_external(self.root/'metadata',self.root/'restored','team',self.root/'backend',result['descriptor_sha256'])
        self.assertFalse((self.root/'restored').exists())

    def test_public_cli_restores_from_clean_git_clone_without_project_config(self):
        import json,subprocess,sys
        from pathlib import Path
        validation,approval=self.approved()
        delivery=self.store.seal(self.candidate['id'],validation['id'],approval['id'])
        self.store.config_path.write_text(json.dumps(self.config))
        cli=Path(__file__).parents[1]/'plugins/app-store-creative/scripts/app_store_creative.py'
        result=subprocess.run([sys.executable,str(cli),'archive','externalize','--repo',str(self.root),
            '--delivery-id',delivery['id'],'--backend','team','--backend-root',str(self.root/'backend'),
            '--confirm','EXTERNALIZE'],check=True,capture_output=True,text=True)
        saved=json.loads(result.stdout)
        repository=self.root/'git-source';repository.mkdir()
        shutil.copytree(saved['metadata_path'],repository/'bundle')
        def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
        git('-C',str(repository),'init','--quiet');git('-C',str(repository),'add','bundle')
        git('-C',str(repository),'-c','user.name=Test','-c','user.email=test@example.invalid',
            'commit','--quiet','-m','test: external metadata')
        commit=git('-C',str(repository),'rev-parse','HEAD')
        clone=self.root/'clone';git('clone','--quiet','--no-local',str(repository),str(clone))
        git('-C',str(clone),'checkout','--quiet','--detach',commit)
        shutil.rmtree(delivery['local_path']);shutil.rmtree(self.store.paths.workspace)
        restored=subprocess.run([sys.executable,str(cli),'archive','restore-external','--repo',str(clone),
            '--path','bundle','--destination','restored','--expected-sha256',saved['descriptor_sha256'],
            '--backend','team','--backend-root',str(self.root/'backend'),'--confirm','RESTORE'],
            check=True,capture_output=True,text=True)
        self.assertTrue(json.loads(restored.stdout)['external_retrieval_verified'])
        self.assertEqual(verify_archive(clone/'restored')['manifest_sha256'],delivery['manifest_sha256'])

    def test_independent_remote_metadata_retrieval_proves_exact_external_archive(self):
        import subprocess
        from external_delivery_archive import verify_external_git
        _,result=self.bundle()
        repository=self.root/'repository';repository.mkdir()
        shutil.copytree(self.root/'metadata',repository/'bundle')
        def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
        git('-C',str(repository),'init','--quiet');git('-C',str(repository),'add','bundle')
        git('-C',str(repository),'-c','user.name=Test','-c','user.email=test@example.invalid',
            'commit','--quiet','-m','test: external delivery')
        commit=git('-C',str(repository),'rev-parse','HEAD')
        remote=self.root/'remote.git';git('clone','--quiet','--bare',str(repository),str(remote))
        git('-C',str(repository),'remote','add','origin',str(remote))
        proof=verify_external_git(repository,commit,'bundle',result['descriptor_sha256'],
                                  'team',self.root/'backend','origin')
        self.assertTrue(proof['retrieval_verified']);self.assertEqual(proof['media_mode'],'external')
        self.assertEqual(proof['archive_commit'],commit)
        self.assertEqual(proof['source_scope'],'configured-remote')
        with self.assertRaises(ValueError):
            verify_external_git(repository,commit,'bundle','0'*64,'team',self.root/'backend','origin')
