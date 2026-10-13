"""Native cadence is an upper limit; normalized video remains constant-rate."""
import unittest
from recording_adapters import (validate_native_recording_probe,
                                validate_recording_probe, RecordingContractError)


class NativeCaptureCadenceTests(unittest.TestCase):
    def test_low_native_cadence_is_not_a_constant_rate_delivery(self):
        plan = {'width': 1920, 'height': 1080, 'duration': 20, 'fps': 30}
        probe = {'format': {'duration': '20'}, 'streams': [{
            'codec_type': 'video', 'codec_name': 'h264', 'width': 1920,
            'height': 1080, 'avg_frame_rate': '1/1'}]}
        validate_native_recording_probe(plan, probe)
        with self.assertRaisesRegex(RecordingContractError, 'frame rate'):
            validate_recording_probe(plan, probe)
        probe['format']['duration'] = '1'
        with self.assertRaisesRegex(RecordingContractError, 'duration'):
            validate_native_recording_probe(plan, probe)
