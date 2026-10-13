"""Substituted staging entries are never published or removed as owned data."""
from pathlib import Path
import tempfile
import unittest
import hashlib
from unittest.mock import patch
from safe_staging import staged_file


class SafeStagingTests(unittest.TestCase):
    def test_replaced_staged_file_is_preserved_after_publication_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            destination = root / 'published'
            with self.assertRaisesRegex(ValueError, 'Staged file identity changed'):
                with staged_file(root) as staged:
                    staged.stream.write(b'producer bytes')
                    staged.sync()
                    replaced = root / staged.name
                    replaced.unlink()
                    replaced.write_bytes(b'owner replacement')
                    staged.publish(destination)
            self.assertEqual(replaced.read_bytes(), b'owner replacement')
            self.assertFalse(destination.exists())

    def test_existing_destination_is_preserved_and_owned_staging_is_cleaned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            destination = root / 'published'
            destination.write_bytes(b'owner destination')
            with self.assertRaises(FileExistsError):
                with staged_file(root) as staged:
                    staged.stream.write(b'producer bytes')
                    staged.sync()
                    staged.publish(destination)
            self.assertEqual(destination.read_bytes(), b'owner destination')
            self.assertEqual(list(root.glob('.creative-object-*')), [])

    def test_inspect_does_not_require_python_311_file_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            with staged_file(Path(directory).resolve()) as staged:
                staged.stream.write(b'portable staged bytes')
                with patch('safe_staging.hashlib.file_digest', create=True,
                           side_effect=AttributeError('Unavailable on Python 3.10')):
                    digest, size = staged.inspect()
                self.assertEqual(digest, hashlib.sha256(b'portable staged bytes').hexdigest())
                self.assertEqual(size, len(b'portable staged bytes'))

    def test_publish_flushes_buffered_bytes_without_explicit_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            destination = root / 'published'
            with staged_file(root) as staged:
                staged.stream.write(b'buffered producer bytes')
                staged.publish(destination)
                self.assertEqual(destination.read_bytes(), b'buffered producer bytes')
