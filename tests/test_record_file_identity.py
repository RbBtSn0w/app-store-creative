"""A substituted non-file record must be refused without blocking readers."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
import test_artifact_lifecycle as fixtures


class RecordFileIdentityTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'Requires POSIX named pipes')
    def test_fifo_record_is_rejected_without_opening_a_blocking_stream(self):
        run = self.store.start_run({})
        path = self.store._path('runs', run['id'])
        path.unlink()
        os.mkfifo(path)
        script = """import json,sys
from pathlib import Path
from artifact_lifecycle import Lifecycle
core = Lifecycle(Path(sys.argv[1]), json.loads(sys.argv[2]))
core._read('runs', sys.argv[3])
"""
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts')
        try:
            result = subprocess.run([sys.executable, '-c', script, str(self.root),
                                     json.dumps(self.cfg), run['id']], env=environment,
                                    capture_output=True, text=True, timeout=2)
        except subprocess.TimeoutExpired:
            self.fail('Record reader blocked on a substituted named pipe')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular file', result.stderr)
        self.assertTrue(stat.S_ISFIFO(path.lstat().st_mode))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'Requires POSIX named pipes')
    def test_transaction_metadata_fifo_is_refused_without_hanging(self):
        self.store.start_run({})
        script = """import json,sys
from pathlib import Path
from artifact_lifecycle import Lifecycle
core = Lifecycle(Path(sys.argv[1]), json.loads(sys.argv[2]))
core.start_run({})
"""
        environment = dict(os.environ)
        environment['PYTHONPATH'] = str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts')
        for name in ('owner.json', 'configuration-authority.json', 'write.lock'):
            with self.subTest(name=name):
                path = self.store.paths.workspace / name
                original = path.read_bytes()
                path.unlink()
                os.mkfifo(path)
                try:
                    try:
                        result = subprocess.run([sys.executable, '-c', script, str(self.root),
                                                 json.dumps(self.cfg)], env=environment,
                                                capture_output=True, text=True, timeout=2)
                    except subprocess.TimeoutExpired:
                        self.fail('Transaction blocked on substituted metadata: ' + name)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('regular file', result.stderr)
                    self.assertTrue(stat.S_ISFIFO(path.lstat().st_mode))
                finally:
                    path.unlink()
                    path.write_bytes(original)

    def test_replaced_lock_after_acquisition_refuses_before_creating_records(self):
        import fcntl
        from unittest.mock import patch
        self.store.start_run({})
        records = self.store.paths.workspace / 'records'
        before = {path: path.read_bytes() for path in records.rglob('*.json')}
        lock = self.store.paths.workspace / 'write.lock'
        original = fcntl.flock
        def acquire(stream, operation):
            original(stream, operation)
            if operation == fcntl.LOCK_EX:
                replacement = lock.with_name('replacement.lock')
                replacement.write_bytes(b'')
                replacement.replace(lock)
        with patch('artifact_lifecycle.fcntl.flock', side_effect=acquire):
            with self.assertRaisesRegex(ValueError, 'lock identity changed'):
                self.store.start_run({})
        self.assertEqual({path: path.read_bytes() for path in records.rglob('*.json')}, before)
