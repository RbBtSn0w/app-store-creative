import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_v2_workflow import create_mock_png
import validator


class ValidatorPNGIntegrityTests(unittest.TestCase):
    def test_rejects_incomplete_or_corrupt_pixels_on_every_host(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.png'
            create_mock_png(path, 64, 64)
            original = path.read_bytes()
            corrupt = bytearray(original)
            corrupt[45] ^= 1
            for data in (original[:-12], bytes(corrupt)):
                for available in (None, '/usr/bin/sips'):
                    with self.subTest(truncated=len(data) != len(original), sips=available):
                        path.write_bytes(data)
                        with mock.patch.object(validator.shutil, 'which', return_value=available), mock.patch.object(
                            validator.subprocess, 'run', return_value=mock.Mock(stdout='metadata 64')
                        ):
                            with self.assertRaises(ValueError):
                                validator.read_image_meta(path)

    def test_valid_rgb_and_alpha_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.png'
            for alpha in (False, True):
                create_mock_png(path, 64, 32, has_alpha=alpha)
                self.assertEqual(validator.read_image_meta(path), (64, 32, alpha))
