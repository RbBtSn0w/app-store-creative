"""Config-driven video production uses the same evidenced preview executor."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import video_engine


class VideoExecutionContractTests(unittest.TestCase):
    def test_config_video_delegates_to_evidenced_executor(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / 'capture.mov').write_bytes(b'fixture recording')
            (root / 'creative.config.json').write_text(json.dumps({
                'targets': ['mac_16_10'], 'previewVideo': {'enabled': True,
                'source': 'capture.mov', 'orientation': 'landscape'}}))
            def execute(contract, output, receipt, frames):
                for path in (output, receipt, frames):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'fixture')
                return {'output': {'probe': {'fixture': True}}, 'tools': {'fixture': True}}
            with mock.patch('produce_app_preview.execute', side_effect=execute) as executor:
                result = video_engine.produce_preview_from_config(root)
            self.assertEqual(executor.call_count, 1)
            contract, output, receipt, frames = executor.call_args.args
            self.assertEqual((contract['width'], contract['height']), (1920, 1080))
            self.assertEqual(result['receipt_path'], str(receipt))
            self.assertEqual(result['frames_path'], str(frames))
            self.assertEqual(result['probe'], {'fixture': True})

    def test_general_export_registers_portable_video_evidence_dependencies(self):
        import production_lifecycle
        from artifact_lifecycle import Lifecycle
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch).resolve()
            (root / 'capture.mov').write_bytes(b'fixture recording')
            config = {'project': {'id': 'video-contract', 'name': 'Video Contract',
                      'bundleId': 'example.video.contract', 'locales': ['en-US']},
                      'targets': ['mac_16_10'], 'cards': [{'id': 'hero'}],
                      'previewVideo': {'enabled': True, 'source': 'capture.mov', 'orientation': 'landscape',
                      'posterRequired': True, 'posterFrameTimeCode': '00:00:05:15'}}
            cfg = root / 'creative.config.json'; cfg.write_text(json.dumps(config))
            def render(*args, **kwargs):
                path = kwargs['output_dir'] / 'en-US/mac_16_10/hero.png'
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture screenshot')
                return {'status': 'PASS', 'artifacts': [{'path': str(path), 'name': 'en-US/mac_16_10/hero.png'}]}
            def encode(contract, output, receipt, frames):
                for path in (output, receipt, frames):
                    path.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b'fixture preview'); frames.write_bytes(b'fixture frames')
                data = {'tools': {'fixture': 'test-only'}, 'contract': contract,
                        'output': {'path': str(output), 'probe': {}},
                        'acceptance_snapshot': {'path': str(frames)}}
                receipt.write_text(json.dumps(data))
                return data
            def extract(source, output, timestamp):
                self.assertEqual(timestamp, 5.5)
                output.write_bytes(b'fixture poster')
                return {'tools': {'fixture': 'test-only'}, 'width': 1920, 'height': 1080}
            # Media validation is outside this dependency-registration contract.
            with mock.patch('export_engine.run_export', side_effect=render), \
                 mock.patch('produce_app_preview.execute', side_effect=encode), \
                 mock.patch('managed_poster.extract', side_effect=extract), \
                 mock.patch.object(Lifecycle, 'validate_candidate', return_value={'status': 'PASS'}):
                result = production_lifecycle.produce(root, cfg, with_video=True)
            core = Lifecycle.from_configuration(root, cfg)
            candidate = core._read('candidates', result['candidate_id'])
            artifacts = [core.verify_artifact(identity) for identity in candidate['artifacts']]
            preview = next(a for a in artifacts if a['role'] == 'preview')
            poster = next(a for a in artifacts if a['role'] == 'poster')
            self.assertIn(preview['id'], poster['inputs'])
            dependencies = [core.verify_artifact(identity) for identity in preview['inputs']]
            receipt = next(a for a in dependencies if a['logical_path'] == 'evidence/preview-receipt.json')
            payload = core.object_path(receipt['sha256']).read_bytes()
            self.assertNotIn(str(root).encode(), payload)
            frame_records = [core.verify_artifact(identity) for identity in receipt['inputs']]
            self.assertTrue(any(a['logical_path'] == 'evidence/preview-frames.png' for a in frame_records))
            self.assertEqual(core._read('attempts', preview['attempt_id'], 'outcome')['status'], 'succeeded')

    def test_required_poster_without_time_code_refuses_before_production(self):
        import production_lifecycle
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            config = {'project': {'id': 'poster-invalid', 'name': 'Poster Invalid',
                      'bundleId': 'example.poster.invalid', 'locales': ['en-US']},
                      'targets': ['mac_16_10'], 'cards': [{'id': 'hero'}],
                      'previewVideo': {'enabled': True, 'source': 'capture.mov', 'posterRequired': True}}
            (root / 'creative.config.json').write_text(json.dumps(config))
            with mock.patch('export_engine.run_export') as renderer:
                with self.assertRaisesRegex(ValueError, 'time code'):
                    production_lifecycle.produce(root, with_video=True)
                renderer.assert_not_called()
            self.assertFalse((root / '.creative').exists())

    def test_poster_time_code_uses_frames_and_refuses_out_of_range_values(self):
        from managed_poster import timestamp_from_time_code
        self.assertEqual(timestamp_from_time_code('00:00:05:15', 30), 5.5)
        for code, fps in [('00:00:05:30', 30), ('00:60:00:00', 30),
                          ('00:00:60:00', 30), ('5.5', 30), ('00:00:05:00', True)]:
            with self.subTest(code=code, fps=fps), self.assertRaises(ValueError):
                timestamp_from_time_code(code, fps)

    def test_failed_and_cancelled_video_preserve_partial_bytes_and_diagnostics(self):
        import production_lifecycle
        from artifact_lifecycle import Lifecycle
        for failure, status in [(RuntimeError('encode failed'), 'failed'),
                                (KeyboardInterrupt(), 'cancelled')]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as scratch:
                root = Path(scratch).resolve()
                (root / 'capture.mov').write_bytes(b'fixture recording')
                config = {'project': {'id': 'video-failure', 'name': 'Video Failure',
                          'bundleId': 'example.video.failure', 'locales': ['en-US']},
                          'targets': ['mac_16_10'], 'cards': [{'id': 'hero'}],
                          'previewVideo': {'enabled': True, 'source': 'capture.mov', 'orientation': 'landscape'}}
                cfg = root / 'creative.config.json'; cfg.write_text(json.dumps(config))
                def fail(contract, output, receipt, frames):
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b'partial video')
                    raise failure
                with mock.patch('export_engine.run_export', return_value={'status': 'PASS', 'artifacts': []}), \
                     mock.patch('produce_app_preview.execute', side_effect=fail):
                    with self.assertRaises(type(failure)):
                        production_lifecycle.produce(root, cfg, with_video=True)
                core = Lifecycle.from_configuration(root, cfg)
                attempts = list((core.paths.workspace / 'records/attempts').iterdir())
                self.assertEqual(len(attempts), 1)
                self.assertEqual(core._read('attempts', attempts[0].name, 'outcome')['status'], status)
                records = [core.verify_artifact(p.stem) for p in (core.paths.workspace / 'records/artifacts').glob('*.json')]
                partial = next(a for a in records if a['role'] == 'preview')
                self.assertTrue(partial['partial'])
                self.assertEqual(core.object_path(partial['sha256']).read_bytes(), b'partial video')
                diagnostic = next(a for a in records if a['role'] == 'diagnostic')
                details = json.loads(core.object_path(diagnostic['sha256']).read_bytes())
                self.assertEqual(details['failure_type'], type(failure).__name__)
                self.assertEqual(details['status'], status)
                self.assertEqual(list((core.paths.workspace / 'records/candidates').glob('*.json')), [])
