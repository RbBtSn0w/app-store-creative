"""Run on a macOS host with Apple Vision to verify actual OCR and box placement."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'plugins/app-store-creative/scripts/app_store_creative.py'


class CaptureCopyAcceptance(unittest.TestCase):
    def test_present_and_absent_phrases(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            shutil.copyfile(ROOT / 'tests/fixtures/capture-copy-english.png', project / 'capture.png')
            config = {'project': {'id': 'ocr-test', 'name': 'OCR test', 'bundleId': 'example.ocr'},
                      'cards': [{'id': 'search', 'headline': 'History', 'screenshot': 'capture.png'}],
                      'targets': ['mac_16_10']}
            (project / 'creative.config.json').write_text(json.dumps(config))
            command = [sys.executable, str(CLI), 'input', '--repo', str(project), 'check-copy',
                       '--locale', 'en-US', '--target', 'mac_16_10', '--card', 'search', '--phrase']
            def locate(phrase):
                result = subprocess.run([*command, phrase], capture_output=True, text=True, timeout=100)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            found = locate('search clipboard')
            self.assertEqual(len(found['matches']), 1)
            line = found['matches'][0]
            self.assertIn('search clipboard', line['text'].lower())
            # The fixture places its only text near the upper left.
            self.assertTrue(0 < line['x'] < .2 and 0 < line['y'] < .4, line)
            self.assertTrue(0 < line['width'] <= 1 - line['x'] and 0 < line['height'] <= 1 - line['y'], line)
            absent = locate('Export invoice')
            self.assertEqual(absent['capture_sha256'], found['capture_sha256'])
            self.assertEqual(absent['matches'], [])


if __name__ == '__main__':
    unittest.main()
