"""Managed capture imports survive external storage and portable sealing."""
import json
from pathlib import Path
import unittest
from unittest import mock
import test_production_lifecycle as fixtures
import artifact_lifecycle as lifecycle
import production_lifecycle
import studio_contract


class InputTests(unittest.TestCase):
    setUp = fixtures.ProductionLifecycleTests.setUp
    renderer = fixtures.ProductionLifecycleTests.renderer

    def test_import_records_attempt_source_and_custom_workspace(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', actor='owner')
        artifact = core.verify_artifact(imported['artifact_id'])
        self.assertEqual(artifact['role'], 'capture')
        self.assertEqual(core.status(imported['run_id'])['attempts'][0]['outcome']['status'], 'succeeded')
        self.assertFalse((self.root / '.creative').exists())
        self.assertEqual(studio_contract.local_asset(self.root, imported['path'], self.config).read_bytes(), (self.root / 'capture.png').read_bytes())
        self.assertEqual(core.plan_cleanup(retention_days=0)['objects'], [])

    def test_external_objects_remain_resolvable_and_package_portable(self):
        self.config['archivePolicy'] = {'schema_version': 1, 'mediaMode': 'git'}
        self.config['storage'] = {'workspaceRoot': str(self.root.parent / (self.root.name + '-external'))}
        self.cfg.write_text(json.dumps(self.config))
        self.addCleanup(__import__('shutil').rmtree, Path(self.config['storage']['workspaceRoot']), True)
        core = lifecycle.Lifecycle(self.root, self.config)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', actor='owner')
        self.config['cards'][0]['screenshot'] = imported['path']
        self.cfg.write_text(json.dumps(self.config))
        with mock.patch('export_engine.run_export', side_effect=self.renderer):
            result = production_lifecycle.produce(self.root)
        self.assertEqual(result['status'], 'PASS', result['validation'].get('errors'))
        core = lifecycle.Lifecycle(self.root, self.config)
        approval = core.approve_design(result['candidate_id'], result['validation']['id'], 'owner', 'human:design')
        delivery = core.seal(result['candidate_id'], result['validation']['id'], approval['id'])
        self.assertTrue(lifecycle.verify_archive(Path(delivery['local_path']))['recipe_verified'])

    def test_inventory_distinguishes_registered_changed_and_unknown_files(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        run = core.start_run({}); attempt = core.start_attempt(run['id'], 'render', 'agent')
        source = core.work_path(attempt['id']) / 'source.bin'; source.write_bytes(b'original')
        core.register(attempt['id'], source, 'source')
        unknown = source.with_name('unknown.bin'); unknown.write_bytes(b'unknown')
        inventory = core.inventory()
        self.assertIn(str(source), inventory['registered_files'])
        self.assertNotIn(str(source), inventory['unregistered_files'])
        source.write_bytes(b'changed')
        inventory = core.inventory()
        self.assertIn(str(source), inventory['changed_files'])
        self.assertIn(str(unknown), inventory['unregistered_files'])

    def test_corrupt_import_fails_before_creating_attempt(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        with self.assertRaises(ValueError):
            core.import_capture(b'not an image', 'capture.png', actor='owner')
        self.assertFalse(core.paths.workspace.exists())

    def test_studio_import_serves_registered_bytes_and_manages_configuration_backup(self):
        import base64
        import urllib.request
        import export_engine
        with export_engine.LocalServerContext(self.root, self.cfg) as server:
            base = f'http://127.0.0.1:{server.port}'
            original = (self.root / 'capture.png').read_bytes()
            request = urllib.request.Request(base + '/api/assets', data=json.dumps({
                'name': 'capture.png', 'data': base64.b64encode(original).decode()}).encode(),
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                imported = json.load(response)
            with urllib.request.urlopen(base + imported['path']) as response:
                self.assertEqual(response.read(), original)
                self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.config['cards'][0]['screenshot'] = imported['path']
            before = self.cfg.read_bytes()
            request = urllib.request.Request(base + '/api/config', data=json.dumps(self.config).encode(),
                headers={'Content-Type': 'application/json', 'If-Match': studio_contract.revision(self.cfg)})
            with urllib.request.urlopen(request) as response:
                self.assertTrue(json.load(response)['ok'])
        core = lifecycle.Lifecycle(self.root, self.config)
        backups = [core._read('artifacts', p.stem) for p in (core.paths.workspace / 'records/artifacts').glob('*.json')]
        backup = next(item for item in backups if item['role'] == 'configuration')
        self.assertEqual(core.object_path(backup['sha256']).read_bytes(), before)
        self.assertFalse((self.root / '.creative').exists())

    def test_cli_import_records_same_managed_input(self):
        import subprocess
        import sys
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        process = subprocess.run([sys.executable, str(cli), 'input', 'import', '--repo', str(self.root),
            '--source', 'capture.png', '--actor', 'owner'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        imported = json.loads(process.stdout)
        core = lifecycle.Lifecycle(self.root, self.config)
        self.assertEqual(core.resolve_import(imported['path'])[0]['id'], imported['id'])

    def test_discard_releases_unused_input_pin_and_preserves_reason(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', 'owner')
        disposition = core.discard_input(imported['id'], actor='owner', reason='Wrong source language')
        self.assertEqual(disposition['reason'], 'Wrong source language')
        self.assertEqual(len(core.plan_cleanup(retention_days=0)['objects']), 1)
        self.assertEqual(core.plan_cleanup()['objects'], [])
        self.assertEqual(core.input_status(imported['id'])['status'], 'discarded')
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            core.discard_input(imported['id'], actor='owner', reason='Rewrite')

    def test_live_configuration_keeps_discarded_input_protected(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', 'owner')
        core.discard_input(imported['id'], actor='owner', reason='Removed from library')
        self.config['cards'][0]['screenshot'] = imported['path']
        self.cfg.write_text(json.dumps(self.config))
        self.assertEqual(core.plan_cleanup(retention_days=0)['objects'], [])

    def test_configuration_edit_invalidates_old_cleanup_plan(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', 'owner')
        core.discard_input(imported['id'], actor='owner', reason='Unused')
        plan = core.plan_cleanup(retention_days=0)
        self.config['cards'][0]['screenshot'] = imported['path']
        self.cfg.write_text(json.dumps(self.config))
        with self.assertRaisesRegex(ValueError, 'stale'):
            core.quarantine_cleanup(plan['id'], actor='owner', reason='Expire unused')
        core.verify_artifact(imported['artifact_id'])

    def test_open_incident_keeps_discarded_input(self):
        core = lifecycle.Lifecycle(self.root, self.config)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', 'owner')
        core.discard_input(imported['id'], actor='owner', reason='Unused')
        incident = core.open_incident(actor='owner', reason='Investigate capture', artifacts=[imported['artifact_id']])
        self.assertEqual(core.plan_cleanup(retention_days=0)['objects'], [])
        core.close_incident(incident['id'], actor='owner', resolution='Investigation complete')
        self.assertEqual(len(core.plan_cleanup(retention_days=0)['objects']), 1)

    def test_workspace_rejects_another_configuration_authority(self):
        core = lifecycle.Lifecycle(self.root, self.config, self.cfg)
        core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', 'owner')
        other_path = self.root / 'other.config.json'; other_path.write_text(json.dumps(self.config))
        other = lifecycle.Lifecycle(self.root, self.config, other_path)
        with self.assertRaisesRegex(ValueError, 'configuration'):
            other.plan_cleanup(retention_days=0)

    def test_cli_discard_preserves_source_and_declared_configuration(self):
        import subprocess
        import sys
        core = lifecycle.Lifecycle(self.root, self.config, self.cfg)
        imported = core.import_capture((self.root / 'capture.png').read_bytes(), 'capture.png', 'owner')
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'input', 'discard', '--repo', str(self.root),
            '--id', imported['id'], '--actor', 'owner', '--reason', 'Unused import', '--confirm', 'DISCARD'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['reason'], 'Unused import')
        self.assertEqual(core.resolve_import(imported['path'])[1].read_bytes(), (self.root / 'capture.png').read_bytes())
