"""Producer payload fingerprints survive archive export without machine paths."""
import json
from pathlib import Path
import tempfile
import unittest
from runtime_identity import snapshot, validate


class RuntimeIdentityTests(unittest.TestCase):
    def test_fingerprint_is_location_independent_and_changes_with_source(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory).resolve() / 'first'; first.mkdir()
            second = Path(directory).resolve() / 'second'; second.mkdir()
            for root in (first, second):
                (root / 'producer.py').write_text('implementation = 1\n')
            self.assertEqual(snapshot(first), snapshot(second))
            (second / 'producer.py').write_text('implementation = 2\n')
            self.assertNotEqual(snapshot(first), snapshot(second))
            self.assertNotIn(directory, json.dumps(snapshot(first)))

    def test_invalid_or_aliased_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            validate({'scheme': 'source-payload-sha256-v1', 'sha256': '0' * 64, 'file_count': True})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'source'; source.write_text('implementation')
            (root / 'producer.py').symlink_to(source)
            with self.assertRaisesRegex(ValueError, 'regular'):
                snapshot(root)

    def test_relative_and_symlinked_directory_resolve_to_same_payload(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'sources'; source.mkdir()
            (source / 'producer.py').write_text('implementation = 1')
            alias = root / 'alias'; alias.symlink_to(source, target_is_directory=True)
            self.assertEqual(snapshot(alias), snapshot(source))
            relative = Path(os.path.relpath(source))
            self.assertEqual(snapshot(relative), snapshot(source))
