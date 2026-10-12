"""Studio poster requests bind effective storage and reviewed layers."""
import unittest
import urllib.error
from unittest import mock
import test_configuration_studio_save as fixtures
import export_engine
from artifact_lifecycle import Lifecycle
from test_v2_workflow import create_mock_png


class LayeredStudioPosterTests(unittest.TestCase):
    setUp = fixtures.LayeredStudioSaveTests.setUp
    tearDown = fixtures.LayeredStudioSaveTests.tearDown
    request = fixtures.LayeredStudioSaveTests.request
    local = fixtures.LayeredStudioSaveTests.local

    def test_local_poster_uses_editor_revision_and_rejects_changed_local_authority(self):
        local = self.local(); original = local.read_bytes(); shared = self.cfg.read_bytes()
        core = Lifecycle.from_configuration(self.root, self.cfg); run = core.start_run({})
        attempt = core.start_attempt(run['id'], 'preview', 'fixture')
        video = self.root/'preview.mp4'; video.write_bytes(b'fixture')
        preview = core.register(attempt['id'], video, 'preview'); core.finish_attempt(attempt['id'], 'succeeded')
        payload = {'run_id':run['id'], 'preview_id':preview['id'], 'timestamp':3}
        def extract(source, output, timestamp):
            create_mock_png(output, 1920, 1080)
            return {'width':1920, 'height':1080, 'duration':15}
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = self.request(ctx, '/api/config')
            with mock.patch('managed_poster.extract', side_effect=extract) as executor:
                result, _ = self.request(ctx, '/api/preview/poster', payload, {'If-Match':headers['ETag']})
                artifact = core.verify_artifact(result['result']['poster_artifact_id'])
                self.assertEqual(artifact['role'], 'poster')
                self.assertEqual(local.read_bytes(), original)
                self.assertEqual(self.cfg.read_bytes(), shared)
                executor.reset_mock(); self.local('changed host')
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/preview/poster', payload, {'If-Match':headers['ETag']})
                self.assertEqual(failure.exception.code, 409); failure.exception.close()
                executor.assert_not_called()
        self.assertFalse((self.root/'.creative').exists())
