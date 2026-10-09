"""Native preview execution registers immutable inputs, outputs and failures."""
import json
from unittest.mock import patch
import unittest
import test_artifact_lifecycle as fixtures


class ManagedPreviewTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def contract(self):
        (self.root / 'take.mp4').write_bytes(b'real take fixture')
        path = self.root / 'timeline.json'; path.write_text(json.dumps({'segments': [{'path': 'take.mp4', 'duration': 20}]}))
        return path

    def test_snapshot_provenance_and_outputs_are_registered(self):
        from managed_preview import produce
        run = self.store.start_run({}); contract = self.contract()
        def executor(recipe, output, receipt, snapshot):
            self.assertNotEqual(recipe['segments'][0]['path'], str(self.root / 'take.mp4'))
            output.write_bytes(b'encoded preview'); receipt.write_text('{}'); snapshot.write_bytes(b'frames')
        with patch('produce_app_preview.execute', side_effect=executor):
            result = produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
        self.assertEqual(result['status'], 'succeeded')
        preview = self.store.verify_artifact(result['preview_artifact_id'])
        self.assertEqual(preview['role'], 'preview')
        self.assertGreaterEqual(len(preview['inputs']), 2)
        self.assertEqual(self.store.status(run['id'])['attempts'][0]['outcome']['status'], 'succeeded')

    def test_failed_executor_preserves_partial_output_and_reason(self):
        from managed_preview import produce
        run = self.store.start_run({}); contract = self.contract()
        def executor(recipe, output, receipt, snapshot):
            output.write_bytes(b'partial'); raise ValueError('Encoding failed')
        with patch('produce_app_preview.execute', side_effect=executor):
            with self.assertRaisesRegex(ValueError, 'Encoding failed'):
                produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
        status = self.store.status(run['id'])
        self.assertEqual(status['attempts'][0]['outcome']['status'], 'failed')
        artifacts = [self.store._read('artifacts', path.stem) for path in (self.store.paths.workspace / 'records/artifacts').glob('*.json')]
        self.assertTrue(any(item['role'] == 'preview' and item['partial'] for item in artifacts))

    def test_preview_closure_contains_portable_receipt_and_frames(self):
        from managed_preview import produce
        from pathlib import Path
        run = self.store.start_run({}); contract = self.contract()
        def executor(recipe, output, receipt, snapshot):
            output.write_bytes(b'encoded'); snapshot.write_bytes(b'frames')
            receipt.write_text(json.dumps({'sources':[{'path':recipe['segments'][0]['path']}],
                'output':{'path':str(output)}, 'acceptance_snapshot':{'path':str(snapshot)},
                'command':['/opt/homebrew/bin/ffmpeg','-i',recipe['segments'][0]['path'],str(output)]}))
        with patch('produce_app_preview.execute', side_effect=executor):
            result = produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
        closure = self.store._closure([result['preview_artifact_id']])
        evidence = [item for item in closure.values() if item['role'] == 'producer-evidence']
        self.assertEqual(len(evidence), 2)
        record = next(item for item in evidence if item['logical_path'].endswith('.json'))
        data = self.store.object_path(record['sha256']).read_text()
        self.assertNotIn(str(self.root), data)
        self.assertNotIn('/opt/homebrew', data)
        self.assertEqual(json.loads(data)['output']['path'], 'media/preview/app_preview.mp4')

    def test_artifact_input_keeps_original_evidence_in_closure(self):
        from managed_preview import produce
        run = self.store.start_run({}); contract = self.contract()
        attempt = self.store.start_attempt(run['id'], 'capture-video', 'agent')
        evidence = self.root / 'recording.json'; evidence.write_text('{}')
        receipt = self.store.register(attempt['id'], evidence, 'producer-evidence', logical_path='evidence/recording.json')
        capture = self.store.register(attempt['id'], self.root / 'take.mp4', 'capture', inputs=[receipt['id']], logical_path='sources/take.mp4')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        contract.write_text(json.dumps({'segments': [{'artifact_id': capture['id'], 'duration': 20}]}))
        def executor(recipe, output, receipt, snapshot):
            self.assertNotIn('artifact_id', recipe['segments'][0])
            self.assertTrue(recipe['segments'][0]['path'].endswith('input-0.mp4'))
            output.write_bytes(b'encoded'); receipt.write_text('{}'); snapshot.write_bytes(b'frames')
        with patch('produce_app_preview.execute', side_effect=executor):
            result = produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
        closure = self.store._closure([result['preview_artifact_id']])
        self.assertIn(capture['id'], closure)
        self.assertIn(receipt['id'], closure)

    def test_incomplete_partial_and_ambiguous_inputs_are_rejected(self):
        from managed_preview import produce
        for case in ('unfinished', 'partial', 'ambiguous', 'failed'):
            with self.subTest(case=case):
                run = self.store.start_run({}); contract = self.contract()
                attempt = self.store.start_attempt(run['id'], 'capture-video', 'agent')
                capture = self.store.register(attempt['id'], self.root / 'take.mp4', 'capture', partial=case == 'partial')
                if case != 'unfinished':
                    self.store.finish_attempt(attempt['id'], 'failed' if case == 'failed' else 'succeeded', 'Fixture failure' if case == 'failed' else None)
                item = {'artifact_id': capture['id'], 'duration': 20}
                if case == 'ambiguous':
                    item['path'] = 'take.mp4'
                contract.write_text(json.dumps({'segments': [item]}))
                with patch('produce_app_preview.execute') as executor:
                    with self.assertRaisesRegex(ValueError, 'completed capture|either path or artifact_id'):
                        produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
                    executor.assert_not_called()

    def test_registered_snapshot_can_be_reused_without_losing_media_identity(self):
        from managed_preview import produce
        run = self.store.start_run({}); contract = self.contract()
        attempt = self.store.start_attempt(run['id'], 'capture-video', 'agent')
        original = self.store.register(attempt['id'], self.root / 'take.mp4', 'capture')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        contract.write_text(json.dumps({'segments': [{'artifact_id': original['id'], 'duration': 20}]}))
        def executor(recipe, output, receipt, snapshot):
            self.assertTrue(recipe['segments'][0]['path'].endswith('.mp4'))
            output.write_bytes(b'encoded'); receipt.write_text('{}'); snapshot.write_bytes(b'frames')
        with patch('produce_app_preview.execute', side_effect=executor):
            first = produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
        closure = self.store._closure([first['preview_artifact_id']])
        capture = next(item for item in closure.values() if item['role'] == 'capture' and item['attempt_id'] == first['attempt_id'])
        self.assertEqual(capture['name'], 'input-0.mp4')
        self.assertEqual(capture['media_type'], 'video/mp4')
        contract.write_text(json.dumps({'segments': [{'artifact_id': capture['id'], 'duration': 20}]}))
        with patch('produce_app_preview.execute', side_effect=executor):
            second = produce(self.store, run['id'], contract, 'preview/app_preview.mp4', 'agent')
        self.assertIn(capture['id'], self.store._closure([second['preview_artifact_id']]))
