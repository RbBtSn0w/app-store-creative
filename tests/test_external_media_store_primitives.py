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


    def test_replaced_destination_parent_preserves_unknown_file(self):
        import shutil
        from unittest.mock import patch
        source = self.root/'source'; source.write_bytes(b'known media')
        parent = self.root/'destination'; parent.mkdir()
        displaced = self.root/'displaced'; foreign = self.root/'foreign'; foreign.mkdir()
        original = shutil.copyfileobj
        sentinel = []
        def replace_parent(stream, output):
            original(stream, output)
            staged = next(parent.glob('.creative-object-*'))
            parent.rename(displaced)
            parent.symlink_to(foreign, target_is_directory=True)
            note = foreign/staged.name; note.write_bytes(b'owner data')
            sentinel.append(note)
        with patch('external_media_store.shutil.copyfileobj', side_effect=replace_parent):
            with self.assertRaises((ValueError, OSError)):
                self.backend._copy(source, parent/'output',
                    hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_size)
        self.assertTrue(sentinel[0].exists(), 'Failure cleanup removed unregistered owner data')
        self.assertEqual(sentinel[0].read_bytes(), b'owner data')
        self.assertFalse((foreign/'output').exists())
