"""Portable producer evidence excludes free-form media metadata."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from managed_preview import portable_receipt
from produce_app_preview import probe_media


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Requires FFmpeg')
class PortableProbePrivacyTests(unittest.TestCase):
    def test_real_source_metadata_stays_out_of_portable_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / 'inputs'
            inputs.mkdir()
            source = inputs / 'source.mp4'
            marker = 'synthetic-private-source-comment'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=size=32x32:rate=30', '-t', '1', '-c:v', 'libx264',
                            '-metadata', 'comment=' + marker, str(source)], check=True)
            probe = probe_media(source)
            self.assertIn(marker, json.dumps(probe))
            original = json.dumps(probe, sort_keys=True)
            receipt = portable_receipt({'sources': [{'path': str(source), 'probe': probe}]}, inputs, [])
            self.assertNotIn(marker, json.dumps(receipt))
            self.assertEqual(json.dumps(probe, sort_keys=True), original)
            facts = receipt['sources'][0]['probe']
            self.assertEqual(facts['streams'][0]['width'], 32)
            self.assertEqual(facts['format']['duration'], probe['format']['duration'])
            self.assertEqual(receipt['sources'][0]['path'], 'recipe/inputs/sources/source.mp4')
