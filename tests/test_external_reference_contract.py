"""External reference field validation remains independent of record commits."""
import tempfile
from pathlib import Path
import unittest
from external_media_store import FileSystemMediaStore


class ExternalReferenceContractTests(unittest.TestCase):
    def test_invalid_reference_fields_are_rejected_without_backend_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            store = FileSystemMediaStore('team', root)
            sha = 'a' * 64
            reference = {'schema_version': 1, 'provider': 'filesystem', 'backend': 'team',
                         'object_id': 'sha256:' + sha, 'version': sha, 'sha256': sha, 'size_bytes': 1}
            self.assertTrue(store.object_path(reference).is_relative_to(root))
            for change in ({'root': str(root)}, {'backend': '/private/backend'},
                           {'version': 'other'}, {'sha256': '0' * 64},
                           {'size_bytes': True}, {'schema_version': True}, {'provider': 'unknown'}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'reference'):
                    store.object_path({**reference, **change})
                self.assertEqual(list(root.iterdir()), [])
