"""Native takes remain immutable while normalized capture has exact cadence."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from media_tool_identity import MediaTools


class RecordingNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tools = MediaTools()
        self.raw = self.root/'native.mov'
        subprocess.run([self.tools.paths['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=navy:s=320x180:r=24:d=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-an', str(self.raw)], check=True, capture_output=True)
        self.plan = {'width':320, 'height':180, 'fps':30, 'duration':2}

    def test_normalized_media_preserves_native_take_and_binds_tools(self):
        from recording_normalization import normalize
        original = self.raw.read_bytes(); output = self.root/'take.mov'
        result = normalize(self.plan, self.raw, output, self.tools)
        self.assertEqual(self.raw.read_bytes(), original)
        self.assertEqual(result['native_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(result['output_sha256'], MediaTools.digest(output))
        probe = result['probe']; video = probe['streams'][0]
        self.assertEqual(video['avg_frame_rate'], '30/1')
        self.assertAlmostEqual(float(probe['format']['duration']), 2, places=2)
        self.assertEqual({t['name'] for t in result['tools']}, {'ffmpeg','ffprobe'})

    def test_existing_output_preserved(self):
        from recording_normalization import normalize
        output = self.root/'take.mov'; output.write_bytes(b'owned')
        with self.assertRaises(ValueError): normalize(self.plan, self.raw, output, self.tools)
        self.assertEqual(output.read_bytes(), b'owned')

    def test_short_native_take_not_padded_to_fake_success(self):
        from recording_normalization import normalize
        self.plan['duration'] = 10
        with self.assertRaisesRegex(ValueError, 'duration'):
            normalize(self.plan, self.raw, self.root/'take.mov', self.tools)
        self.assertFalse((self.root/'take.mov').exists())

    def test_invalid_or_private_tool_identity_rejected(self):
        from recording_adapters import validate_normalization_tools
        base = [{'name':'ffmpeg','version':'9.0','executable_sha256':'a'*64},
                {'name':'ffprobe','version':'9.0','executable_sha256':'b'*64}]
        self.assertEqual(validate_normalization_tools(base), base)
        for value in ([], [base[0], base[0]], [{**base[0], 'path':'/private/tool'}, base[1]],
                      [{**base[0], 'version':'/private/version'}, base[1]]):
            with self.assertRaises(ValueError): validate_normalization_tools(value)

    def test_native_tail_is_bounded_while_final_duration_stays_strict(self):
        from recording_adapters import validate_native_recording_probe, validate_recording_probe
        probe = {'format':{'duration':'4'}, 'streams':[{'codec_type':'video',
            'codec_name':'h264','width':320,'height':180,'avg_frame_rate':'24/1'}]}
        validate_native_recording_probe(self.plan, probe)
        with self.assertRaises(ValueError): validate_recording_probe(self.plan, probe)
        probe['format']['duration'] = '13'
        with self.assertRaisesRegex(ValueError, 'duration'):
            validate_native_recording_probe(self.plan, probe)
