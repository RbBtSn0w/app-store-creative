"""Invalid recorder receipts retain diagnostic bytes only as partial artifacts."""
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
import managed_recording


class RecordingReceiptBoundaryTests(unittest.TestCase):
    def test_invalid_tools_never_register_complete_native_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory).resolve()
            registrations = []
            def register(*args, **kwargs):
                registrations.append(kwargs.get('partial', False))
                return {'id': 'artifact'}
            core = SimpleNamespace(start_attempt=lambda *args: {'id': 'attempt', 'work_path': str(work)},
                                   keep_lease=lambda *args: nullcontext(), register=register,
                                   finish_attempt=lambda *args: None)
            def recorder(plan, output, receipt):
                output.write_bytes(b'normalized')
                native = output.with_name('take.native.mov'); native.write_bytes(b'native')
                sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
                probe = {'format': {'duration': '20'}, 'streams': [{'codec_type': 'video',
                         'codec_name': 'h264', 'width': 1920, 'height': 1080, 'avg_frame_rate': '30/1'}]}
                receipt.write_text(json.dumps({'plan': plan, 'output': {'sha256': sha(output), 'probe': probe},
                    'native_output': {'sha256': sha(native)}, 'normalization': {
                        'native_sha256': sha(native), 'output_sha256': sha(output),
                        'native_probe': probe, 'tools': [], 'command': []}}))
            with patch.object(managed_recording, 'run_recorder', side_effect=recorder):
                with self.assertRaisesRegex(ValueError, 'normalization tools'):
                    managed_recording.record(core, 'run', 'example.dev', 1, 20, 1920, 1080,
                                             30, 'preview.mov', 'owner')
            self.assertEqual(registrations, [True, True])
