"""Retrieval deadlines stop owned process groups and span multiple commands."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import subprocess
import test_publication_lifecycle
import delivery_lifecycle


class RetrievalProcessBudgetTests(unittest.TestCase):
    def test_timeout_stops_descendant_even_when_it_ignores_termination(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / 'heartbeat'
            child = "import signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); p=pathlib.Path(" + repr(str(heartbeat)) + ");\nwhile True:\n p.write_text(str(time.monotonic())); time.sleep(.02)"
            parent = "import subprocess,time,sys; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(30)"
            runner = delivery_lifecycle.RetrievalCommands(os.environ.copy(), budget=2)
            with self.assertRaisesRegex(ValueError, 'timed out'):
                runner.run([sys.executable, '-c', parent], timeout=.4)
            self.assertTrue(heartbeat.exists())
            stopped = heartbeat.read_text()
            time.sleep(.15)
            self.assertEqual(heartbeat.read_text(), stopped)

    def test_exited_leader_does_not_leave_pipe_owning_child_running(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / 'heartbeat'
            child = "import time,pathlib; p=pathlib.Path(" + repr(str(heartbeat)) + ");\nwhile True:\n p.write_text(str(time.monotonic())); time.sleep(.02)"
            parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child) + "])"
            runner = delivery_lifecycle.RetrievalCommands(os.environ.copy(), budget=2)
            with self.assertRaisesRegex(ValueError, 'timed out'):
                runner.run([sys.executable, '-c', parent], timeout=.4)
            self.assertTrue(heartbeat.exists())
            stopped = heartbeat.read_text()
            time.sleep(.15)
            self.assertEqual(heartbeat.read_text(), stopped)

    def test_keyboard_cancellation_stops_running_process_and_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / 'heartbeat'
            command = "import time,pathlib; p=pathlib.Path(" + repr(str(heartbeat)) + ");\nwhile True:\n p.write_text(str(time.monotonic())); time.sleep(.02)"
            def cancel(process, **options):
                deadline = time.monotonic() + 2
                while not heartbeat.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(heartbeat.exists())
                raise KeyboardInterrupt()
            runner = delivery_lifecycle.RetrievalCommands(os.environ.copy(), budget=3)
            with patch.object(subprocess.Popen, 'communicate', new=cancel):
                with self.assertRaises(KeyboardInterrupt):
                    runner.run([sys.executable, '-c', command])
            stopped = heartbeat.read_text()
            time.sleep(.15)
            self.assertEqual(heartbeat.read_text(), stopped)

    def test_commands_share_one_total_deadline(self):
        runner = delivery_lifecycle.RetrievalCommands(os.environ.copy(), budget=.3)
        runner.run([sys.executable, '-c', 'import time; time.sleep(.18)'], timeout=2)
        with self.assertRaisesRegex(ValueError, 'timed out'):
            runner.run([sys.executable, '-c', 'import time; time.sleep(.18)'], timeout=2)
