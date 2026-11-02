"""Configuration temporary cleanup preserves substituted owner files."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import studio_contract


class StudioAtomicJsonTests(unittest.TestCase):
    def test_serialization_failure_leaves_target_and_no_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'creative.config.json'
            target.write_bytes(b'original configuration')
            with self.assertRaises(TypeError):
                studio_contract.atomic_json(target, {'invalid': object()})
            self.assertEqual(target.read_bytes(), b'original configuration')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_partial_write_failure_removes_owned_temporary(self):
        self.assert_failed_write_is_cleaned('write')

    def test_close_failure_removes_owned_temporary(self):
        self.assert_failed_write_is_cleaned('close')

    def assert_failed_write_is_cleaned(self, failure):
        original = tempfile.NamedTemporaryFile

        class FailingFile:
            def __init__(self, *args, **kwargs):
                self.file = original(*args, **kwargs)
                self.name = self.file.name

            def __enter__(self):
                return self

            def fileno(self):
                return self.file.fileno()

            def write(self, data):
                if failure == 'write':
                    self.file.write(data[:len(data) // 2])
                    raise OSError('fixture partial write failed')
                return self.file.write(data)

            def __exit__(self, *_args):
                self.file.close()
                if failure == 'close':
                    raise OSError('fixture close failed')

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'creative.config.json'
            target.write_bytes(b'original configuration')
            with patch.object(tempfile, 'NamedTemporaryFile', FailingFile):
                with self.assertRaisesRegex(OSError, 'fixture .* failed'):
                    studio_contract.atomic_json(target, {'fixture': True})
            self.assertEqual(target.read_bytes(), b'original configuration')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_replacement_failure_removes_owned_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'creative.config.json'
            target.write_bytes(b'original configuration')
            with patch.object(Path, 'replace', side_effect=OSError('fixture replace failed')):
                with self.assertRaisesRegex(OSError, 'fixture replace failed'):
                    studio_contract.atomic_json(target, {'fixture': True})
            self.assertEqual(target.read_bytes(), b'original configuration')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_success_replaces_target_and_removes_temporary(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'creative.config.json'
            studio_contract.atomic_json(target, {'fixture': 'Unicode 字符'})
            self.assertEqual(json.loads(target.read_text()), {'fixture': 'Unicode 字符'})
            self.assertEqual(list(Path(directory).iterdir()), [target])

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
