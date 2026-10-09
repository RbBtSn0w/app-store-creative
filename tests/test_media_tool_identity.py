"""Portable media tool evidence binds pinned executables and detects replacement."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_delivery_lifecycle
from media_tool_identity import MediaTools


class MediaToolIdentityTests(unittest.TestCase):
    def test_version_and_hash_are_portable_and_replacement_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in ('ffmpeg', 'ffprobe'):
                path = root / name
                path.write_text('#!/bin/sh\necho "' + name + ' version 8.0-test build"\n')
                path.chmod(0o700)
            with patch('media_tool_identity.shutil.which', side_effect=lambda name: str(root / name)):
                tools = MediaTools()
            self.assertEqual([item['name'] for item in tools.evidence], ['ffmpeg', 'ffprobe'])
            self.assertNotIn(directory, json.dumps(tools.evidence))
            self.assertEqual(tools.paths['ffmpeg'], str(root / 'ffmpeg'))
            tools.verify()
            (root / 'ffmpeg').write_text('changed binary')
            with self.assertRaisesRegex(ValueError, 'changed during production'):
                tools.verify()

    def test_missing_tool_never_creates_invented_version(self):
        with patch('media_tool_identity.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                MediaTools()
