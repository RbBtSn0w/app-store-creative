"""Existing capture imports preserve the original acquisition dependency."""
import json
import unittest
from unittest import mock
from artifact_lifecycle import Lifecycle
import production_lifecycle as production
import test_production_lifecycle as fixtures


class CaptureArtifactImportTests(unittest.TestCase):
    setUp = fixtures.ProductionLifecycleTests.setUp
    renderer = fixtures.ProductionLifecycleTests.renderer

    def capture(self, role='capture'):
        core = Lifecycle.from_configuration(self.root, self.cfg)
        run = core.start_run({'stage': 'capture'})
        attempt = core.start_attempt(run['id'], 'capture', 'fixture')
        artifact = core.register(attempt['id'], self.root/'capture.png', role, logical_path='acquisition/capture.png')
        core.finish_attempt(attempt['id'], 'succeeded')
        return core, artifact

    def test_original_capture_remains_in_production_dependency_chain(self):
        core, original = self.capture()
        imported = core.import_capture_artifact(original['id'], 'fixture')
        self.assertEqual(core.verify_artifact(imported['artifact_id'])['inputs'], [original['id']])
        config = json.loads(self.cfg.read_text())
        config['cards'][0]['screenshot'] = imported['path']
        self.cfg.write_text(json.dumps(config))
        with mock.patch('export_engine.run_export', side_effect=self.renderer):
            result = production.produce(self.root)
        self.assertEqual(result['status'], 'PASS')
        core = Lifecycle.from_configuration(self.root, self.cfg)
        sources = [core._read('artifacts', p.stem) for p in
                   (core.paths.workspace/'records/artifacts').glob('*.json')]
        self.assertTrue(any(a['run_id'] == result['run_id'] and
                            imported['artifact_id'] in a['inputs'] for a in sources))

    def test_non_capture_rejected_before_new_run(self):
        core, original = self.capture('source')
        before = set((core.paths.workspace/'records/runs').glob('*.json'))
        with self.assertRaisesRegex(ValueError, 'capture'):
            core.import_capture_artifact(original['id'], 'fixture')
        self.assertEqual(set((core.paths.workspace/'records/runs').glob('*.json')), before)

    def test_damaged_object_rejected_before_new_run(self):
        core, original = self.capture()
        core.object_path(original['sha256']).write_bytes(b'damaged')
        before = set((core.paths.workspace/'records/runs').glob('*.json'))
        with self.assertRaises(ValueError):
            core.import_capture_artifact(original['id'], 'fixture')
        self.assertEqual(set((core.paths.workspace/'records/runs').glob('*.json')), before)

    def test_cli_import_accepts_registered_capture_without_source_copy(self):
        import app_store_creative as cli
        core, original = self.capture()
        args = cli.build_parser().parse_args(['input', 'import', '--repo', str(self.root),
            '--artifact', original['id'], '--actor', 'fixture'])
        imported = cli.run(args)
        self.assertEqual(core.verify_artifact(imported['artifact_id'])['inputs'], [original['id']])

    def test_failed_acquisition_rejected_before_new_run(self):
        core = Lifecycle.from_configuration(self.root, self.cfg)
        run = core.start_run({'stage': 'capture'})
        attempt = core.start_attempt(run['id'], 'capture', 'fixture')
        artifact = core.register(attempt['id'], self.root/'capture.png', 'capture',
                                 logical_path='acquisition/capture.png')
        core.finish_attempt(attempt['id'], 'failed', reason='Acquisition failed')
        before = set((core.paths.workspace/'records/runs').glob('*.json'))
        with self.assertRaisesRegex(ValueError, 'did not succeed'):
            core.import_capture_artifact(artifact['id'], 'fixture')
        self.assertEqual(set((core.paths.workspace/'records/runs').glob('*.json')), before)

    def test_partial_capture_rejected_even_after_successful_attempt(self):
        core = Lifecycle.from_configuration(self.root, self.cfg)
        run = core.start_run({'stage': 'capture'})
        attempt = core.start_attempt(run['id'], 'capture', 'fixture')
        artifact = core.register(attempt['id'], self.root/'capture.png', 'capture', partial=True,
                                 logical_path='acquisition/capture.png')
        core.finish_attempt(attempt['id'], 'succeeded')
        before = set((core.paths.workspace/'records/runs').glob('*.json'))
        with self.assertRaisesRegex(ValueError, 'complete capture'):
            core.import_capture_artifact(artifact['id'], 'fixture')
        self.assertEqual(set((core.paths.workspace/'records/runs').glob('*.json')), before)

    def test_capture_without_archive_path_rejected_before_new_run(self):
        core = Lifecycle.from_configuration(self.root, self.cfg)
        run = core.start_run({'stage': 'capture'})
        attempt = core.start_attempt(run['id'], 'capture', 'fixture')
        artifact = core.register(attempt['id'], self.root/'capture.png', 'capture')
        core.finish_attempt(attempt['id'], 'succeeded')
        before = set((core.paths.workspace/'records/runs').glob('*.json'))
        with self.assertRaisesRegex(ValueError, 'logical path'):
            core.import_capture_artifact(artifact['id'], 'fixture')
        self.assertEqual(set((core.paths.workspace/'records/runs').glob('*.json')), before)
