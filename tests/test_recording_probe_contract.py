"""Recording media must satisfy the planned dimensions, cadence and duration."""
import copy
import unittest
import test_artifact_lifecycle
from recording_adapters import validate_recording_probe

class RecordingProbeTests(unittest.TestCase):
    def test_valid_fractional_rate_and_bounded_duration(self):
        plan = {'width': 1920, 'height': 1080, 'fps': 30, 'duration': 15}
        probe = {'format': {'duration': '14.97'}, 'streams': [{'codec_type': 'video',
            'codec_name': 'h264', 'width': 1920, 'height': 1080, 'avg_frame_rate': '30000/1001'}]}
        validate_recording_probe(plan, probe)

    def test_wrong_dimensions_codec_rate_duration_and_multiple_video_fail(self):
        plan = {'width': 1920, 'height': 1080, 'fps': 30, 'duration': 15}
        base = {'format': {'duration': '15'}, 'streams': [{'codec_type': 'video',
            'codec_name': 'h264', 'width': 1920, 'height': 1080, 'avg_frame_rate': '30/1'}]}
        for field, value in [('width', 1280), ('codec_name', 'hevc'), ('avg_frame_rate', '0/0'),
                             ('avg_frame_rate', '60/1'), ('duration', 'NaN'), ('duration', '1'),
                             ('multiple', True)]:
            with self.subTest(field=field, value=value):
                probe = copy.deepcopy(base)
                if field == 'duration': probe['format']['duration'] = value
                elif field == 'multiple': probe['streams'].append(copy.deepcopy(probe['streams'][0]))
                else: probe['streams'][0][field] = value
                with self.assertRaisesRegex(ValueError, 'Recording media'):
                    validate_recording_probe(plan, probe)
