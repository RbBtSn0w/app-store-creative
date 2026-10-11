"""Opt-in real macOS capture proves readiness timing and machine-readable output."""
import json
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest


BUNDLE = os.environ.get('CREATIVE_NATIVE_TEST_BUNDLE_ID')
WINDOW = os.environ.get('CREATIVE_NATIVE_TEST_WINDOW_ID')


def wait_for_start(process, timeout=30):
    deadline = time.monotonic() + timeout
    line = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stderr, selectors.EVENT_READ)
        while len(line) < 4096:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError('Native recording readiness deadline exceeded')
            chunk = os.read(process.stderr.fileno(), 1)
            if not chunk:
                raise RuntimeError('Native recorder exited before a complete readiness signal')
            if chunk == b'\n':
                return line.decode().strip()
            line.extend(chunk)
    raise ValueError('Native recording readiness signal exceeds 4096 bytes')


class ReadinessDeadlineTests(unittest.TestCase):
    def test_complete_signal_preserves_later_stderr(self):
        process = subprocess.Popen([sys.executable, '-c',
            'import sys; sys.stderr.write("RECORDING_STARTED\\nRECORDING_FINISHED\\n")'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(wait_for_start(process), 'RECORDING_STARTED')
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(stderr, 'RECORDING_FINISHED\n')
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)

    def test_partial_signal_without_newline_times_out(self):
        process = subprocess.Popen([sys.executable, '-c',
            'import sys,time; sys.stderr.write("RECORDING_"); sys.stderr.flush(); time.sleep(1)'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with self.assertRaises(TimeoutError):
                wait_for_start(process, timeout=0.05)
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)


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
                self.assertEqual(wait_for_start(process), 'RECORDING_STARTED')
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
