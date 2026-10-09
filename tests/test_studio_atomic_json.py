"""Configuration temporary cleanup preserves substituted owner files."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import studio_contract


class StudioAtomicJsonTests(unittest.TestCase):
    def test_replacement_failure_preserves_substituted_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'creative.config.json'
            target.write_bytes(b'original configuration')
            replacements = []
            def replace(source, destination):
                source.rename(source.with_name(source.name + '-original'))
                source.write_bytes(b'owner temporary')
                replacements.append(source)
                raise OSError('fixture replacement failed')
            with patch.object(Path, 'replace', replace):
                with self.assertRaisesRegex(OSError, 'fixture replacement failed'):
                    studio_contract.atomic_json(target, {'fixture': True})
            self.assertEqual(target.read_bytes(), b'original configuration')
            self.assertEqual(replacements[0].read_bytes(), b'owner temporary')
