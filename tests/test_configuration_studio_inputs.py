"""Studio capture import and managed read views share effective storage."""
import base64
import json
import unittest
import urllib.request
import test_configuration_studio_save as fixtures
import export_engine
from artifact_lifecycle import Lifecycle
from test_v2_workflow import create_mock_png


class LayeredStudioInputTests(unittest.TestCase):
    setUp = fixtures.LayeredStudioSaveTests.setUp
    tearDown = fixtures.LayeredStudioSaveTests.tearDown
    request = fixtures.LayeredStudioSaveTests.request
    local = fixtures.LayeredStudioSaveTests.local

    def test_import_and_read_views_use_same_local_workspace_without_rewriting_config(self):
        local = self.local('host 素材'); original = self.cfg.read_bytes(), local.read_bytes()
        source = self.root/'capture.png'; create_mock_png(source, 12, 24); raw = source.read_bytes()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            imported, _ = self.request(ctx, '/api/assets', {'name':'capture.png', 'data':base64.b64encode(raw).decode()})
            core = Lifecycle.from_configuration(self.root, self.cfg)
            _, registered = core.resolve_import(imported['path'])
            self.assertEqual(registered.read_bytes(), raw)
            with urllib.request.urlopen(f'http://127.0.0.1:{ctx.port}/' + imported['path']) as response:
                self.assertEqual(response.read(), raw)
            runs, _ = self.request(ctx, '/api/runs')
            self.assertEqual(runs, core.list_runs())
            self.assertEqual(runs['runs'][0]['id'], imported['run_id'])
            detail, _ = self.request(ctx, '/api/runs/' + imported['run_id'])
            self.assertEqual(detail, core.status(imported['run_id']))
            self.request(ctx, '/api/inventory')
            self.request(ctx, '/api/deliveries')
        self.assertFalse((self.root/'.creative').exists())
        self.assertEqual((self.cfg.read_bytes(), local.read_bytes()), original)
