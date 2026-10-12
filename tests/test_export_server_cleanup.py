import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import export_engine


class ExportServerCleanupTests(unittest.TestCase):
    def test_health_failure_releases_owned_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            context = export_engine.LocalServerContext(Path(directory), Path(directory) / 'creative.config.json')
            try:
                with mock.patch.object(export_engine.urllib.request, 'urlopen', side_effect=OSError('probe failed')), mock.patch.object(export_engine.time, 'sleep'):
                    with self.assertRaisesRegex(RuntimeError, 'failed to become ready'):
                        context.__enter__()
                with socket.socket() as probe:
                    self.assertNotEqual(probe.connect_ex(('127.0.0.1', context.port)), 0)
                self.assertFalse(context.thread.is_alive())
            finally:
                context.__exit__(None, None, None)
