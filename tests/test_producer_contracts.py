"""Producer contracts retained independently of the retired task engine."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "plugins/app-store-creative/scripts"
sys.path.insert(0, str(SCRIPTS))
import recording_adapters as adapters
import produce_app_preview as preview


class ProducerContractTests(unittest.TestCase):
    def test_recording_adapters_are_strict_and_side_effect_free(self):
        self.assertEqual(adapters.ios_simulator_command("ABC-123", Path("preview.mov"))[:5],
                         ["xcrun", "simctl", "io", "ABC-123", "recordVideo"])
        with self.assertRaises(adapters.RecordingContractError):
            adapters.macos_screencapturekit_contract(bundle_id="com.example", output=Path("a.mov"), capture_scope="desktop")
        with self.assertRaises(adapters.RecordingContractError):
            adapters.macos_screencapturekit_contract(bundle_id="com.example", output=Path("a.mov"), include_cursor=True)

    def test_preview_dry_run_supports_silent_segments_and_timed_overlay(self):
        contract = {"width": 1080, "height": 1920, "fps": 30, "duration": 5,
                    "segments": [{"path": "silent.mov", "duration": 5, "has_audio": False}],
                    "overlays": [{"type": "text", "text": "Hello", "start": 1, "end": 3}]}
        command = preview.build_command(contract, Path("preview.mp4"))
        joined = " ".join(command)
        self.assertIn("anullsrc", joined); self.assertIn("drawtext", joined)
        self.assertIn("libx264", command); self.assertIn("aac", command)

    def test_preview_supports_image_overlay_end_card_and_rejects_duration_drift(self):
        contract = {"width": 1080, "height": 1920, "fps": 30, "duration": 6,
                    "segments": [{"path": "segment.mov", "duration": 5, "has_audio": False}],
                    "overlays": [{"type": "image", "path": "badge.png", "start": 1, "end": 3, "x": 10, "y": 20}],
                    "end_card": {"path": "end.png", "duration": 1}}
        command = preview.build_command(contract, Path("preview.mp4")); joined = " ".join(command)
        self.assertIn("badge.png", command); self.assertIn("end.png", command); self.assertIn("overlay=x=10:y=20", joined)
        contract["duration"] = 7
        with self.assertRaisesRegex(ValueError, "durations"):
            preview.build_command(contract, Path("preview.mp4"))

    def test_preview_selects_source_interval_and_rejects_invalid_start(self):
        contract = {"width": 1920, "height": 1080, "fps": 30, "duration": 4,
                    "segments": [{"path": "take.mov", "start": 8, "duration": 4, "has_audio": True}]}
        command = preview.build_command(contract, Path("preview.mp4"))
        filters = command[command.index("-filter_complex") + 1]
        self.assertIn("trim=start=8.0:duration=4.0", filters)
        self.assertIn("atrim=start=8.0:duration=4.0", filters)
        for start in (-1, float("nan"), float("inf")):
            contract["segments"][0]["start"] = start
            with self.assertRaises(ValueError):
                preview.build_command(contract, Path("preview.mp4"))

    def test_recording_plan_requires_explicit_window_and_bounded_duration(self):
        plan = adapters.macos_recording_plan(bundle_id="com.example.app", window_id=42,
                                            output=Path("take.mov"), duration=20)
        self.assertEqual(plan["window_id"], 42)
        self.assertEqual(plan["duration"], 20)
        self.assertFalse(plan["include_cursor"])
        for duration in (0, -1, float("nan"), 3601):
            with self.assertRaises(adapters.RecordingContractError):
                adapters.macos_recording_plan(bundle_id="com.example.app", window_id=42,
                                             output=Path("take.mov"), duration=duration)
        with self.assertRaises(adapters.RecordingContractError):
            adapters.macos_recording_plan(bundle_id="com.example.app", window_id=0,
                                         output=Path("take.mov"), duration=20)

    def test_preview_rejects_out_of_bounds_sources_and_missing_audio(self):
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch) / "take.mov"; source.write_bytes(b"real-source-fixture")
            contract = {"segments": [{"path": str(source), "start": 8, "duration": 4, "has_audio": False}]}
            media = {"format": {"duration": "10"}, "streams": [{"codec_type": "video"}]}
            with mock.patch.object(preview, "probe_media", return_value=media):
                with self.assertRaisesRegex(ValueError, "exceeds"):
                    preview.preflight_sources(contract)
                contract["segments"][0]["start"] = 6
                result = preview.preflight_sources(contract)
                self.assertEqual(result[0]["sha256"], preview.digest(source))
                contract["segments"][0]["has_audio"] = True
                with self.assertRaisesRegex(ValueError, "no audio"):
                    preview.preflight_sources(contract)

    def test_preview_preserves_existing_outputs(self):
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "preview.mp4"; output.write_bytes(b"previous-preview")
            contract = {"width": 1920, "height": 1080, "fps": 30, "duration": 4,
                        "segments": [{"path": "take.mov", "duration": 4, "has_audio": False}]}
            with self.assertRaisesRegex(ValueError, "overwrite"):
                preview.execute(contract, output, output.with_suffix(".json"), output.with_suffix(".png"))
            self.assertEqual(output.read_bytes(), b"previous-preview")


    def test_preview_preserves_outputs_created_during_encoding(self):
        import subprocess
        for owned_name in ('preview.mp4', 'receipt.json', 'snapshot.png'):
            with self.subTest(owned_name=owned_name), tempfile.TemporaryDirectory() as scratch:
                root = Path(scratch).resolve()
                output, receipt, snapshot = (root / name for name in ('preview.mp4', 'receipt.json', 'snapshot.png'))
                owner = root / owned_name
                class FixtureTools:
                    paths = {'ffmpeg': 'fixture-ffmpeg'}
                    evidence = []
                    def verify(self):
                        owner.write_bytes(b'owner bytes')
                def run(command, **options):
                    if '-filters' not in command:
                        Path(command[-1]).write_bytes(b'encoded fixture')
                    return subprocess.CompletedProcess(command, 0, '', '')
                contract = {'width': 64, 'height': 64, 'fps': 30, 'duration': 1,
                            'segments': [{'path': 'fixture.mov', 'duration': 1, 'has_audio': False}]}
                with mock.patch('media_tool_identity.MediaTools', FixtureTools), \
                     mock.patch.object(preview, 'preflight_sources', return_value=[]), \
                     mock.patch.object(preview, 'validate_output', return_value={}), \
                     mock.patch.object(preview.subprocess, 'run', side_effect=run):
                    with self.assertRaises(OSError):
                        preview.execute(contract, output, receipt, snapshot)
                self.assertEqual(owner.read_bytes(), b'owner bytes')
