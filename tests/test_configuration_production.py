"""Screenshot production and observations share protected layered authority."""
import json
import unittest
from unittest import mock
import test_production_lifecycle as fixtures
import production_lifecycle as production
from artifact_lifecycle import Lifecycle


class LayeredProductionTests(unittest.TestCase):
    setUp = fixtures.ProductionLifecycleTests.setUp
    renderer = fixtures.ProductionLifecycleTests.renderer

    def local(self):
        path = self.root/'creative.config.local.json'
        path.write_text(json.dumps({'schema_version':1,'project_id':'demo','storage':{'workspaceRoot':'host work'}}))
        return path

    def test_production_and_latest_bind_local_roots_and_revision(self):
        local = self.local(); original = self.cfg.read_bytes(), local.read_bytes()
        from configuration_layers import load
        revision = '"' + load(self.root, self.cfg).revision + '"'
        with mock.patch('export_engine.run_export', side_effect=self.renderer):
            result = production.produce(self.root, expected_revision=revision)
        self.assertEqual(result['validation']['status'], 'PASS')
        self.assertEqual(production.latest(self.root)['candidate_id'], result['candidate_id'])
        core = Lifecycle.from_configuration(self.root, self.cfg)
        self.assertEqual(core._run(result['run_id'])['configuration_layers']['sources']['workspaceRoot'], 'local')
        self.assertFalse((self.root/'managed').exists())
        self.assertEqual((self.cfg.read_bytes(), local.read_bytes()), original)

    def test_local_change_during_render_refuses_candidate_promotion(self):
        local = self.local()
        def render(*args, **kwargs):
            result = self.renderer(*args, **kwargs)
            local.write_text(json.dumps({'schema_version':1,'project_id':'demo','storage':{'workspaceRoot':'other host'}}))
            return result
        with mock.patch('export_engine.run_export', side_effect=render):
            with self.assertRaisesRegex(ValueError, 'layers.*changed|Inputs changed'):
                production.produce(self.root)
        self.assertFalse(list((self.root/'host work/records/candidates').glob('*.json')))

    def test_studio_export_and_status_share_editor_revision_and_local_candidate(self):
        import export_engine
        from test_studio_release import StudioReleaseTests
        self.local()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = StudioReleaseTests.request(self, ctx, '/api/config')
            with mock.patch('export_engine.run_export', side_effect=self.renderer):
                result, _ = StudioReleaseTests.request(self, ctx, '/api/export', {'scope':'all'}, {'If-Match':headers['ETag']})
            self.assertTrue(result['ok'])
            status, _ = StudioReleaseTests.request(self, ctx, '/api/status')
            self.assertEqual(status['candidate_id'], result['result']['candidate_id'])
            self.assertEqual(status['configRevision'], headers['ETag'])
            self.assertNotIn('error', status)
        self.assertFalse((self.root/'managed').exists())

    def test_imported_local_capture_produces_with_original_source_dependency(self):
        self.local()
        core = Lifecycle.from_configuration(self.root, self.cfg)
        imported = core.import_capture((self.root/'capture.png').read_bytes(), 'capture.png', 'fixture')
        config = json.loads(self.cfg.read_text()); config['cards'][0]['screenshot'] = imported['path']
        self.cfg.write_text(json.dumps(config))
        with mock.patch('export_engine.run_export', side_effect=self.renderer):
            result = production.produce(self.root)
        self.assertEqual(result['status'], 'PASS')
        core = Lifecycle.from_configuration(self.root, self.cfg)
        source_records = [core._read('artifacts', path.stem)
                          for path in (core.paths.workspace/'records/artifacts').glob('*.json')]
        matching = [item for item in source_records if item['run_id'] == result['run_id']
                    and item['role'] == 'source' and item['logical_path'] == imported['path'].lstrip('/')]
        self.assertEqual(len(matching), 1)
        self.assertIn(imported['artifact_id'], matching[0]['inputs'])
        self.assertFalse((self.root/'managed').exists())
