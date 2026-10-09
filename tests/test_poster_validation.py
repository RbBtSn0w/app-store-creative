"""Independent media validation enforces the declared poster contract."""
import contextlib
import io
import json
from unittest.mock import patch
import unittest
import test_artifact_lifecycle as fixtures
from test_v2_workflow import create_mock_png
import validator

class PosterValidationTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def validate(self, size=None):
        cfg = self.root / 'creative.config.json'
        create_mock_png(self.root / 'source.png', 2880, 1800)
        cfg.write_text(json.dumps({'project':{'locales':['en-US']}, 'targets':['mac_16_10'],
            'cards':[{'id':'hero','screenshot':'source.png'}],
            'previewVideo':{'enabled':True,'posterRequired':True,'source':'source.mp4','duration':15}}))
        (self.root / 'source.mp4').write_bytes(b'fixture video')
        media = self.root / 'media'; (media / 'en-US/mac_16_10').mkdir(parents=True)
        create_mock_png(media / 'en-US/mac_16_10/hero.png',2880,1800)
        (media / 'preview').mkdir(); (media / 'preview/app_preview.mp4').write_bytes(b'fixture preview')
        if size:
            create_mock_png(media / 'preview/poster.png', *size)
        probe = {'format':{'duration':'15'},'streams':[{'codec_type':'video','codec_name':'h264',
            'r_frame_rate':'30/1','width':1920,'height':1080}, {'codec_type':'audio','codec_name':'aac'}]}
        with patch('validator.inspect_video_file', return_value=probe), contextlib.redirect_stdout(io.StringIO()):
            return validator.run_validation(self.root,cfg,media)

    def test_required_poster_is_checked_without_candidate_records(self):
        result = self.validate()
        self.assertTrue(any('Missing declared poster' in error for error in result['errors']))

    def test_poster_dimensions_must_match_verified_preview(self):
        result = self.validate((320,180))
        self.assertTrue(any('Poster dimensions must match' in error for error in result['errors']))

    def test_matching_poster_passes_local_media_gate(self):
        result = self.validate((1920,1080))
        self.assertEqual(result['errors'], [])
