"""ASC responses provide facts without claiming playback or poster readiness."""
import unittest
import json
from asc_observation_adapter import preview_facts


class AscObservationAdapterTests(unittest.TestCase):
    def response(self, image=None):
        return {'versionLocalizationId': 'localization', 'sets': [
            {'set': {'type': 'appPreviewSets', 'id': 'set'}, 'previews': [
                {'type': 'appPreviews', 'id': 'preview', 'attributes': {
                    'sourceFileChecksum': 'a' * 32,
                    'assetDeliveryState': {'state': 'COMPLETE'},
                    'previewFrameTimeCode': '00:00:05:01',
                    'previewImage': image or {'width': 0, 'height': 0}}}]}]}

    def test_complete_upload_with_zero_size_poster_is_not_poster_success(self):
        facts = preview_facts(self.response(), 'localization', 'preview')
        self.assertEqual(facts['processing'], {'processing_state': 'COMPLETE'})
        self.assertEqual(facts['upload']['source_checksum'], 'a' * 32)
        self.assertFalse(facts['poster']['poster_verified'])
        self.assertNotIn('playback', facts)

    def test_positive_dimensions_do_not_prove_image_load(self):
        facts = preview_facts(self.response({'width': 1920, 'height': 1080}), 'localization', 'preview')
        self.assertNotIn('poster_verified', facts['poster'])

    def test_foreign_localization_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'localization'):
            preview_facts(self.response(), 'foreign', 'preview')

    def test_missing_remote_id_is_absence_not_processing_success(self):
        facts = preview_facts(self.response(), 'localization', 'missing')
        self.assertEqual(facts, {'upload': {'found': False}})

    def test_duplicate_remote_identity_is_rejected(self):
        response = self.response()
        response['sets'][0]['previews'] *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            preview_facts(response, 'localization', 'preview')


class BoundAscAdapterTests(unittest.TestCase):
    response = AscObservationAdapterTests.response
    def test_bound_observations_match_plan_without_playback(self):
        from asc_observation_adapter import preview_observations
        plan = {'target': {'app_id': 'app', 'version_id': 'version', 'platform': 'MAC_OS'},
                'assets': [{'artifact_id': 'artifact', 'role': 'preview'}]}
        scope = {'target': plan['target'], 'artifact_id': 'artifact',
                 'localization_id': 'localization', 'remote_id': 'preview',
                 'observed_at': '2026-10-07T01:00:00+00:00', 'evidence_reference': 'asc:read:1'}
        rows = preview_observations(plan, json.dumps(self.response()).encode(), scope)
        self.assertEqual([r['gate'] for r in rows], ['upload', 'processing', 'poster'])
        self.assertTrue(all(r['target'] == plan['target'] and r['source'] == 'asc-cli' for r in rows))
        self.assertFalse(rows[-1]['facts']['poster_verified'])
        with self.assertRaisesRegex(ValueError, 'scope'):
            preview_observations(plan, json.dumps(self.response()).encode(), {**scope, 'target': {'app_id': 'foreign'}})
        with self.assertRaisesRegex(ValueError, 'Preview'):
            preview_observations(plan, json.dumps(self.response()).encode(), {**scope, 'artifact_id': 'foreign'})
