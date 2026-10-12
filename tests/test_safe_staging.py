"""Substituted staging entries are never published or removed as owned data."""
from pathlib import Path
import tempfile
import unittest
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
