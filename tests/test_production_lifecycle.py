"""Production entry points allocate immutable attempts instead of shared outputs."""
import json
from pathlib import Path
import sys
import tempfile
import urllib.request
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import app_store_creative as cli
import artifact_lifecycle as lifecycle
import production_lifecycle as production
import studio_contract as contract
import export_engine
from test_v2_workflow import create_mock_png


class ProductionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        create_mock_png(self.root / 'capture.png', 2880, 1800)
        self.config = {'project': {'id': 'demo', 'name': 'Demo', 'bundleId': 'example.demo', 'locales': ['en-US']},
                       'targets': ['mac_16_10'], 'cards': [{'id': 'hero', 'screenshot': 'capture.png'}],
                       'publishing': {'version': '1.5'}, 'storage': {'workspaceRoot': 'managed'}}
        self.cfg = self.root / 'creative.config.json'; self.cfg.write_text(json.dumps(self.config))

    def test_export_output_override_names_flag_and_storage_migration(self):
        args = cli.build_parser().parse_args(['export', '--repo', str(self.root), '--output-dir', 'outputs'])
        with self.assertRaisesRegex(ValueError, r'--output-dir.*storage.workspaceRoot'):
            cli.run(args)

    def renderer(self, repo_root, config_path=None, output_dir=None, **kwargs):
        output_dir = output_dir or repo_root / 'artifacts'
        output = output_dir / 'en-US/mac_16_10/hero.png'
        create_mock_png(output, 2880, 1800)
        config = json.loads(config_path.read_text())
        record = {'config_hash': contract.digest(config_path.read_bytes()),
                  'source_hashes': contract.input_hashes(repo_root, config)[0],
                  'sha256': contract.digest(output.read_bytes()), 'render_ready': True}
        (output_dir / '.export-evidence.json').write_text(json.dumps({'en-US/mac_16_10/hero.png': record}))
        return {'status': 'PASS', 'artifacts': [{'name': 'en-US/mac_16_10/hero.png', 'path': str(output)}], 'total_rendered': 1}

    def test_two_exports_never_overwrite_previous_attempt(self):
        with mock.patch('export_engine.run_export', side_effect=self.renderer):
            first = production.produce(self.root)
            first_output = Path(first['export']['artifacts'][0]['path']); original = first_output.read_bytes()
            second = production.produce(self.root)
        self.assertNotEqual(first['run_id'], second['run_id'])
        self.assertNotEqual(first['attempt_id'], second['attempt_id'])
        self.assertEqual(first_output.read_bytes(), original)
        self.assertEqual(first['validation']['status'], 'PASS')
        self.assertFalse((self.root / 'artifacts').exists())
        self.assertFalse((self.root / '.creative').exists())

    def test_failed_renderer_has_persistent_reason(self):
        with mock.patch('export_engine.run_export', side_effect=RuntimeError('Font failed')):
            with self.assertRaisesRegex(RuntimeError, 'Font failed'):
                production.produce(self.root)
        records = list((self.root / 'managed/records/attempts').glob('*/outcome.json'))
        self.assertEqual(len(records), 1)
        outcome = json.loads(records[0].read_text())
        self.assertEqual(outcome['status'], 'failed')
        self.assertIn('Font failed', outcome['reason'])

    def test_studio_and_cli_share_managed_output_and_readonly_status(self):
        with export_engine.LocalServerContext(self.root, self.cfg) as server:
            base = f'http://127.0.0.1:{server.port}'
            request = urllib.request.Request(base + '/api/export', data=json.dumps({'scope': 'all'}).encode(),
                headers={'Content-Type': 'application/json', 'If-Match': contract.revision(self.cfg)})
            with mock.patch('export_engine.run_export', side_effect=self.renderer):
                with urllib.request.urlopen(request) as response:
                    body = json.load(response)
            self.assertIn('candidate_id', body['result'])
            before = list((self.root / 'managed/records/validations').glob('*.json'))
            with urllib.request.urlopen(base + '/api/status') as response:
                status = json.load(response)
            self.assertEqual(status['candidate_id'], body['result']['candidate_id'])
            self.assertEqual(status['validation']['status'], 'PASS')
            self.assertEqual(len(list((self.root / 'managed/records/validations').glob('*.json'))), len(before))
            name = 'en-US/mac_16_10/hero.png'
            with urllib.request.urlopen(base + '/api/artifacts/' + status['candidate_id'] + '/' + name) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertTrue(response.read().startswith(b'\x89PNG'))

    def test_changed_source_makes_readonly_status_stale(self):
        with mock.patch('export_engine.run_export', side_effect=self.renderer):
            production.produce(self.root)
        (self.root / 'capture.png').write_bytes(b'changed after export')
        result = production.latest(self.root)
        self.assertEqual(result['validation']['status'], 'STALE')
        self.assertFalse(result['remote_verified'])

    def test_cli_config_option_is_relative_to_project_not_current_directory(self):
        args = cli.build_parser().parse_args(['export', '--repo', str(self.root), '--config', 'creative.config.json'])
        with mock.patch('production_lifecycle.produce', return_value={'status': 'PASS'}) as produce:
            cli.run(args)
        self.assertEqual(produce.call_args.args[1], self.cfg)

    def test_cli_export_uses_managed_production(self):
        args = cli.build_parser().parse_args(['export', '--repo', str(self.root)])
        with mock.patch('production_lifecycle.produce', return_value={'status': 'PASS', 'run_id': 'managed'}) as produce:
            result = cli.run(args)
        self.assertEqual(result['run_id'], 'managed')
        self.assertEqual(produce.call_args.args[0], self.root)

if __name__ == '__main__':
    unittest.main()
