"""Poster extraction preserves the source preview and explicit frame selection."""
import json
from unittest.mock import patch
import unittest
import test_artifact_lifecycle as fixtures

class ManagedPosterTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def preview(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'preview', 'agent')
        path = self.root / 'preview.mp4'; path.write_bytes(b'video fixture')
        artifact = self.store.register(attempt['id'], path, 'preview')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        return run, artifact

    def test_frame_and_receipt_link_to_verified_preview(self):
        from managed_poster import produce
        run, preview = self.preview()
        def extract(source, output, timestamp):
            output.write_bytes(b'png fixture')
            return {'width':1920, 'height':1080, 'duration':15}
        with patch('managed_poster.extract', side_effect=extract):
            result = produce(self.store, run['id'], preview['id'], 3, 'agent')
        closure = self.store._closure([result['poster_artifact_id']])
        self.assertIn(preview['id'], closure)
        receipt = next(item for item in closure.values() if item['role'] == 'producer-evidence')
        data = json.loads(self.store.object_path(receipt['sha256']).read_text())
        self.assertEqual(data['timestamp_seconds'], 3)
        self.assertEqual(data['source_sha256'], preview['sha256'])
        self.assertNotIn(str(self.root), json.dumps(data))
        self.assertFalse(result['approval_granted'])

    def test_invalid_time_does_not_execute(self):
        from managed_poster import produce
        run, preview = self.preview()
        with patch('managed_poster.extract') as executor:
            for timestamp in (-1, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    produce(self.store, run['id'], preview['id'], timestamp, 'agent')
            executor.assert_not_called()

    def test_failure_and_cancellation_keep_selected_time_and_partial_bytes(self):
        from managed_poster import produce
        for error, expected in [(ValueError('Decode failed'), 'failed'), (KeyboardInterrupt(), 'cancelled')]:
            with self.subTest(status=expected):
                run, preview = self.preview()
                def extractor(source, output, timestamp):
                    output.write_bytes(b'partial PNG'); raise error
                with patch('managed_poster.extract', side_effect=extractor):
                    with self.assertRaises(type(error)):
                        produce(self.store, run['id'], preview['id'], 4.5, 'agent')
                attempts = self.store.status(run['id'])['attempts']
                poster_attempt = next(item for item in attempts if item['stage'] == 'poster')
                self.assertEqual(poster_attempt['outcome']['status'], expected)
                artifacts = [self.store._read('artifacts', path.stem)
                    for path in (self.store.paths.workspace / 'records/artifacts').glob('*.json')]
                partial = next(item for item in artifacts if item['attempt_id'] == poster_attempt['id'] and item['role'] == 'poster')
                self.assertTrue(partial['partial'])
                closure = self.store._closure([partial['id']])
                plans = [item for item in closure.values() if item['logical_path'] == 'evidence/poster-plan.json']
                self.assertEqual(len(plans), 1)
                plan = json.loads(self.store.object_path(plans[0]['sha256']).read_text())
                self.assertEqual(plan['timestamp_seconds'], 4.5)
                self.assertEqual(plan['source_sha256'], preview['sha256'])
                with self.assertRaisesRegex(ValueError, 'partial'):
                    self.store.select(run['id'], [partial['id']])
