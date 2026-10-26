"""ASC responses provide facts without claiming playback or poster readiness."""
import unittest
import json
from asc_observation_adapter import preview_facts


class AscObservationAdapterTests(unittest.TestCase):
    def response(self, image=None, **overrides):
        attributes = {'sourceFileChecksum': 'a' * 32,
                      'assetDeliveryState': {'state': 'COMPLETE'},
                      'videoDeliveryState': {'state': 'COMPLETE'},
                      'videoUrl': 'https://apptrailers.example.invalid/preview.m3u8',
                      'previewFrameTimeCode': '00:00:05:01',
                      'previewImage': image or {'width': 0, 'height': 0}}
        for key, value in overrides.items():
            if value is None:
                attributes.pop(key, None)
            else:
                attributes[key] = value
        return {'versionLocalizationId': 'localization', 'sets': [
            {'set': {'type': 'appPreviewSets', 'id': 'set'}, 'previews': [
                {'type': 'appPreviews', 'id': 'preview', 'attributes': attributes}]}]}

    def processing(self, **overrides):
        facts = preview_facts(self.response(**overrides), 'localization', 'preview')
        return facts['processing']['processing_state']

    def test_delivered_asset_with_transcoding_video_is_processing(self):
        # Apple reports the uploaded file before the playable video exists (#57).
        self.assertEqual(self.processing(videoDeliveryState={'state': 'PROCESSING'}, videoUrl=''),
                         'PROCESSING')

    def test_complete_requires_both_states_and_video_url(self):
        self.assertEqual(self.processing(), 'COMPLETE')
        self.assertEqual(self.processing(videoUrl=''), 'PROCESSING')
        self.assertEqual(self.processing(videoUrl=None), 'PROCESSING')

    def test_any_failed_state_is_failure(self):
        self.assertEqual(self.processing(videoDeliveryState={'state': 'FAILED'}), 'FAILED')
        self.assertEqual(self.processing(assetDeliveryState={'state': 'FAILED'}), 'FAILED')

    def test_upload_in_progress_is_not_completion(self):
        self.assertEqual(self.processing(assetDeliveryState={'state': 'UPLOADING'},
                                         videoDeliveryState=None, videoUrl=None), 'UPLOADING')

    def test_modern_response_without_deprecated_asset_state_completes(self):
        self.assertEqual(self.processing(assetDeliveryState=None), 'COMPLETE')
        self.assertEqual(self.processing(assetDeliveryState=None,
                                         videoDeliveryState={'state': 'PROCESSING'}), 'PROCESSING')

    def test_apple_in_flight_states_are_not_unknown(self):
        self.assertEqual(self.processing(videoDeliveryState={'state': 'UPLOAD_COMPLETE'}, videoUrl=''),
                         'PROCESSING')
        self.assertEqual(self.processing(assetDeliveryState={'state': 'AWAITING_UPLOAD'}), 'UPLOADING')

    def test_missing_video_state_is_unknown_not_success(self):
        self.assertEqual(self.processing(videoDeliveryState=None), 'UNKNOWN')

    def test_malformed_video_fields_are_rejected(self):
        for overrides in ({'videoDeliveryState': 'COMPLETE'}, {'videoUrl': 42}):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ValueError, 'Invalid ASC'):
                    preview_facts(self.response(**overrides), 'localization', 'preview')

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
    def test_machine_and_url_references_are_rejected_case_insensitively(self):
        from asc_observation_adapter import preview_observations
        plan = {'target': {'app_id': 'app'},
                'assets': [{'artifact_id': 'artifact', 'role': 'preview'}]}
        scope = {'target': plan['target'], 'artifact_id': 'artifact',
                 'localization_id': 'localization', 'remote_id': 'preview',
                 'observed_at': '2026-10-07T01:00:00+00:00',
                 'evidence_reference': 'asc:read:fixture'}
        for key in ('localization_id', 'remote_id', 'evidence_reference'):
            for value in ('HTTP://example.invalid/private',
                          'hTtPs://example.invalid/private', 'FILE:/private/fixture',
                          'asc:read:http://example.invalid/private', 'asc:read:file:/private/fixture'):
                with self.subTest(field=key, value=value):
                    with self.assertRaisesRegex(ValueError, 'sanitized'):
                        preview_observations(plan, json.dumps(self.response()).encode(),
                                             {**scope, key: value})

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

    def test_video_facts_alias(self):
        from asc_observation_adapter import video_facts, preview_facts
        self.assertIs(video_facts, preview_facts)


class ScreenshotObservationAdapterTests(unittest.TestCase):
    def response(self, image=None):
        return {'versionLocalizationId': 'localization', 'sets': [
            {'set': {'type': 'appScreenshotSets', 'id': 'set'}, 'screenshots': [
                {'type': 'appScreenshots', 'id': 'screenshot-1', 'attributes': {
                    'sourceFileChecksum': 'b' * 32,
                    'assetDeliveryState': {'state': 'COMPLETE'},
                    'imageAsset': image or {'width': 2880, 'height': 1800}}}]}]}

    def test_screenshot_facts_normal(self):
        from asc_observation_adapter import screenshot_facts
        facts = screenshot_facts(self.response(), 'localization', 'screenshot-1')
        self.assertEqual(facts['upload']['source_checksum'], 'b' * 32)
        self.assertEqual(facts['processing']['processing_state'], 'COMPLETE')
        self.assertEqual(facts['media']['image_width'], 2880)
        self.assertEqual(facts['media']['image_height'], 1800)

    def test_screenshot_facts_zero_dimension_fails_media(self):
        from asc_observation_adapter import screenshot_facts
        facts = screenshot_facts(self.response({'width': 0, 'height': 0}), 'localization', 'screenshot-1')
        self.assertFalse(facts['media']['media_verified'])

    def test_screenshot_facts_missing_remote_id(self):
        from asc_observation_adapter import screenshot_facts
        facts = screenshot_facts(self.response(), 'localization', 'missing')
        self.assertEqual(facts, {'upload': {'found': False}})

    def test_screenshot_facts_foreign_localization(self):
        from asc_observation_adapter import screenshot_facts
        with self.assertRaisesRegex(ValueError, 'localization'):
            screenshot_facts(self.response(), 'foreign', 'screenshot-1')

    def test_screenshot_facts_duplicate(self):
        from asc_observation_adapter import screenshot_facts
        resp = self.response()
        resp['sets'][0]['screenshots'] *= 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            screenshot_facts(resp, 'localization', 'screenshot-1')

    def test_screenshot_observations_matches_plan(self):
        from asc_observation_adapter import screenshot_observations
        plan = {'target': {'app_id': 'app', 'version_id': 'version', 'platform': 'MAC_OS'},
                'assets': [{'artifact_id': 'art-shot', 'role': 'screenshot'}]}
        scope = {'target': plan['target'], 'artifact_id': 'art-shot',
                 'localization_id': 'localization', 'remote_id': 'screenshot-1',
                 'observed_at': '2026-10-07T01:00:00+00:00', 'evidence_reference': 'asc:read:1'}
        rows = screenshot_observations(plan, json.dumps(self.response()).encode(), scope)
        self.assertEqual([r['gate'] for r in rows], ['upload', 'processing', 'media'])
        self.assertTrue(all(r['target'] == plan['target'] and r['source'] == 'asc-cli' for r in rows))

    def test_screenshot_observations_rejects_non_screenshot(self):
        from asc_observation_adapter import screenshot_observations
        plan = {'target': {'app_id': 'app', 'version_id': 'version', 'platform': 'MAC_OS'},
                'assets': [{'artifact_id': 'art-preview', 'role': 'preview'}]}
        scope = {'target': plan['target'], 'artifact_id': 'art-preview',
                 'localization_id': 'localization', 'remote_id': 'screenshot-1',
                 'observed_at': '2026-10-07T01:00:00+00:00', 'evidence_reference': 'asc:read:1'}
        with self.assertRaisesRegex(ValueError, 'Screenshot'):
            screenshot_observations(plan, json.dumps(self.response()).encode(), scope)
