"""Opt-in real macOS capture proves readiness timing and machine-readable output."""
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import unittest


BUNDLE = os.environ.get('CREATIVE_NATIVE_TEST_BUNDLE_ID')
WINDOW = os.environ.get('CREATIVE_NATIVE_TEST_WINDOW_ID')


@unittest.skipUnless(platform.system() == 'Darwin' and BUNDLE and WINDOW,
                     'Requires an explicitly authorized seeded native window')
class NativeRecordingSignalTests(unittest.TestCase):
    def test_ready_signal_precedes_completion_and_stdout_is_json(self):
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/record_app_window.py'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'take.mov'
            process = subprocess.Popen([
                sys.executable, str(script), '--bundle-id', BUNDLE,
                '--window-id', WINDOW, '--duration', '5', '--width', '920',
                '--height', '940', '--fps', '30', '--output', str(output),
                '--execute'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True)
            try:
                self.assertEqual(process.stderr.readline().strip(), 'RECORDING_STARTED')
                self.assertIsNone(process.poll(), 'Readiness must arrive during capture')
                stdout, stderr = process.communicate(timeout=90)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertIn('RECORDING_FINISHED', stderr)
                result = json.loads(stdout)
                self.assertTrue(result['executed'])
                receipt = json.loads(Path(result['receipt']).read_text())
                self.assertEqual(receipt['plan']['window_id'], int(WINDOW))
                self.assertGreater(output.stat().st_size, 0)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                process.communicate(timeout=10)
