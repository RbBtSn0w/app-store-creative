"""External objects survive producer loss and restore exact immutable versions."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import test_artifact_lifecycle
from external_media_store import FileSystemMediaStore


class ExternalMediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.backend=FileSystemMediaStore('team-media',self.root/'backend')

    def test_persist_and_independent_retrieval_after_source_is_gone(self):
        source=self.root/'preview.mp4';source.write_bytes(b'actual bytes for storage fixture')
        reference=self.backend.persist(source);source.unlink()
        self.assertNotIn(str(self.root),str(reference))
        self.assertEqual(reference['sha256'],hashlib.sha256(b'actual bytes for storage fixture').hexdigest())
        restarted=FileSystemMediaStore('team-media',self.root/'backend')
        destination=self.root/'restored.mp4';restarted.retrieve(reference,destination)
        self.assertEqual(destination.read_bytes(),b'actual bytes for storage fixture')

    def test_missing_or_corrupt_version_never_falls_back_to_other_content(self):
        source=self.root/'source';source.write_bytes(b'one')
        reference=self.backend.persist(source)
        object_path=self.backend.object_path(reference)
        object_path.write_bytes(b'two')
        with self.assertRaisesRegex(ValueError,'integrity'):
            self.backend.retrieve(reference,self.root/'out')
        self.assertFalse((self.root/'out').exists())
        object_path.unlink()
        with self.assertRaisesRegex(ValueError,'missing'):
            self.backend.retrieve(reference,self.root/'out')

    def test_foreign_backend_and_url_locators_are_rejected(self):
        source=self.root/'source';source.write_bytes(b'one');reference=self.backend.persist(source)
        with self.assertRaises(ValueError):
            self.backend.retrieve({**reference,'backend':'foreign'},self.root/'out')
        with self.assertRaises(ValueError):
            self.backend.retrieve({**reference,'object_id':'https://example.invalid/signed?token=x'},self.root/'out')

    def test_repeated_persistence_is_immutable_and_restoration_never_overwrites(self):
        source=self.root/'source';source.write_bytes(b'one');reference=self.backend.persist(source)
        self.assertEqual(self.backend.persist(source),reference)
        destination=self.root/'owner-file';destination.write_bytes(b'owner')
        with self.assertRaises(ValueError):self.backend.retrieve(reference,destination)
        self.assertEqual(destination.read_bytes(),b'owner')


class ManagedExternalMediaTests(unittest.TestCase):
    setUp=test_artifact_lifecycle.ArtifactLifecycleTests.setUp

    def test_managed_persistence_restores_missing_cas_without_changing_metadata(self):
        run=self.store.start_run({});attempt=self.store.start_attempt(run['id'],'capture','agent')
        source=self.root/'take';source.write_bytes(b'capture')
        artifact=self.store.register(attempt['id'],source,'capture')
        before=self.store._path('artifacts',artifact['id']).read_bytes()
        saved=self.store.persist_external_media(artifact['id'],'team-media',self.root/'external')
        self.store.object_path(artifact['sha256']).unlink()
        restored=self.store.restore_external_media(saved['id'],'team-media',self.root/'external')
        self.assertTrue(restored['restored'])
        self.assertEqual(self.store.verify_artifact(artifact['id'])['sha256'],artifact['sha256'])
        self.assertEqual(self.store._path('artifacts',artifact['id']).read_bytes(),before)
        self.assertEqual(self.store.verify_history()['status'],'PASS')

    def test_public_cli_persists_and_restores_exact_managed_bytes(self):
        import json,subprocess,sys
        run=self.store.start_run({});attempt=self.store.start_attempt(run['id'],'capture','agent')
        source=self.root/'source';source.write_bytes(b'cli capture')
        artifact=self.store.register(attempt['id'],source,'capture')
        self.store.config_path.write_text(json.dumps(self.cfg))
        cli=Path(__file__).parents[1]/'plugins/app-store-creative/scripts/app_store_creative.py'
        common=['--repo',str(self.root),'--backend','team','--backend-root',str(self.root/'external')]
        result=subprocess.run([sys.executable,str(cli),'archive','persist-media',*common,
            '--artifact-id',artifact['id'],'--confirm','PERSIST'],check=True,capture_output=True,text=True)
        reference=json.loads(result.stdout)
        self.store.object_path(artifact['sha256']).unlink()
        restored=subprocess.run([sys.executable,str(cli),'archive','restore-media',*common,
            '--reference-id',reference['id'],'--confirm','RESTORE'],check=True,capture_output=True,text=True)
        self.assertTrue(json.loads(restored.stdout)['restored'])
        self.assertEqual(self.store.verify_history()['status'],'PASS')
