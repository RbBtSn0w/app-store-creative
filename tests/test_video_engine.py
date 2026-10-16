"""Unit tests for video engine dynamic audio detection and preservation."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import produce_app_preview
import video_engine


class VideoEngineAudioDetectionTests(unittest.TestCase):
    def test_probe_video_detects_audio_stream_present(self):
        fake_probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
            ],
            "format": {"duration": "20.0"},
        }
        with mock.patch("video_engine.probe_video", return_value=fake_probe):
            probe = video_engine.probe_video(Path("test.mp4"))
            has_audio = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
            self.assertTrue(has_audio)

    def test_probe_video_detects_no_audio_stream(self):
        fake_probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
            ],
            "format": {"duration": "20.0"},
        }
        with mock.patch("video_engine.probe_video", return_value=fake_probe):
            probe = video_engine.probe_video(Path("test.mp4"))
            has_audio = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
            self.assertFalse(has_audio)

    def test_produce_preview_from_config_preserves_audio_when_present(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "capture.mov").write_bytes(b"dummy")
            (root / "creative.config.json").write_text(json.dumps({
                "targets": ["mac_16_10"],
                "previewVideo": {"enabled": True, "source": "capture.mov", "orientation": "landscape"},
            }))
            fake_probe = {
                "streams": [
                    {"codec_type": "video", "codec_name": "h264"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "20.0"},
            }
            captured_contract = {}

            def fake_execute(contract, output, receipt, frames):
                nonlocal captured_contract
                captured_contract = contract
                for p in (output, receipt, frames):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"data")
                return {"output": {"probe": {}}, "tools": {}}

            with mock.patch("video_engine.probe_video", return_value=fake_probe), \
                 mock.patch("produce_app_preview.execute", side_effect=fake_execute):
                video_engine.produce_preview_from_config(root)

            self.assertTrue(captured_contract["segments"][0]["has_audio"])

    def test_produce_preview_from_config_sets_has_audio_false_when_silent(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "capture.mov").write_bytes(b"dummy")
            (root / "creative.config.json").write_text(json.dumps({
                "targets": ["mac_16_10"],
                "previewVideo": {"enabled": True, "source": "capture.mov", "orientation": "landscape"},
            }))
            fake_probe = {
                "streams": [
                    {"codec_type": "video", "codec_name": "h264"},
                ],
                "format": {"duration": "20.0"},
            }
            captured_contract = {}

            def fake_execute(contract, output, receipt, frames):
                nonlocal captured_contract
                captured_contract = contract
                for p in (output, receipt, frames):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"data")
                return {"output": {"probe": {}}, "tools": {}}

            with mock.patch("video_engine.probe_video", return_value=fake_probe), \
                 mock.patch("produce_app_preview.execute", side_effect=fake_execute):
                video_engine.produce_preview_from_config(root)

            self.assertFalse(captured_contract["segments"][0]["has_audio"])

    def test_produce_preview_from_config_supports_custom_audio_source(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "capture.mov").write_bytes(b"dummy")
            (root / "voiceover.m4a").write_bytes(b"audio-data")
            (root / "creative.config.json").write_text(json.dumps({
                "targets": ["mac_16_10"],
                "previewVideo": {
                    "enabled": True,
                    "source": "capture.mov",
                    "audioSource": "voiceover.m4a",
                    "orientation": "landscape",
                },
            }))
            captured_contract = {}

            def fake_execute(contract, output, receipt, frames):
                nonlocal captured_contract
                captured_contract = contract
                for p in (output, receipt, frames):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"data")
                return {"output": {"probe": {}}, "tools": {}}

            fake_probe = {"streams": [{"codec_type": "video"}]}
            with mock.patch("video_engine.probe_video", return_value=fake_probe), \
                 mock.patch("produce_app_preview.execute", side_effect=fake_execute):
                video_engine.produce_preview_from_config(root)

            self.assertEqual(captured_contract.get("audio_source"), str((root / "voiceover.m4a").resolve()))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
class ProduceAppPreviewAudioIntegrationTests(unittest.TestCase):
    def test_real_audio_preserved_when_present(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "source_with_audio.mp4"
            output = root / "out.mp4"
            receipt = root / "out.receipt.json"
            snapshot = root / "out.png"

            # Create synthetic 1s video with sine audio
            subprocess.run([
                "ffmpeg", "-v", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=blue:s=64x64:r=30:d=1",
                "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
                "-c:v", "libx264", "-c:a", "aac", str(source)
            ], check=True, capture_output=True)

            contract = {
                "width": 64, "height": 64, "fps": 30, "duration": 1,
                "segments": [{"path": str(source), "duration": 1, "has_audio": True}]
            }
            produce_app_preview.execute(contract, output, receipt, snapshot)
            probe = produce_app_preview.probe_media(output)
            audio = next((s for s in probe["streams"] if s.get("codec_type") == "audio"), None)
            self.assertIsNotNone(audio)
            self.assertEqual(audio["codec_name"], "aac")

    def test_fallback_silence_when_source_lacks_audio(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "source_no_audio.mp4"
            output = root / "out.mp4"
            receipt = root / "out.receipt.json"
            snapshot = root / "out.png"

            # Create synthetic 1s video WITHOUT audio
            subprocess.run([
                "ffmpeg", "-v", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=green:s=64x64:r=30:d=1",
                "-c:v", "libx264", str(source)
            ], check=True, capture_output=True)

            contract = {
                "width": 64, "height": 64, "fps": 30, "duration": 1,
                "segments": [{"path": str(source), "duration": 1, "has_audio": False}]
            }
            produce_app_preview.execute(contract, output, receipt, snapshot)
            probe = produce_app_preview.probe_media(output)
            audio = next((s for s in probe["streams"] if s.get("codec_type") == "audio"), None)
            self.assertIsNotNone(audio)
            self.assertEqual(audio["codec_name"], "aac")

    def test_custom_audio_source_applied(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "source.mp4"
            voiceover = root / "voiceover.m4a"
            output = root / "out.mp4"
            receipt = root / "out.receipt.json"
            snapshot = root / "out.png"

            # Create video without audio
            subprocess.run([
                "ffmpeg", "-v", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "color=black:s=64x64:r=30:d=1",
                "-c:v", "libx264", str(source)
            ], check=True, capture_output=True)

            # Create audio file (sine tone)
            subprocess.run([
                "ffmpeg", "-v", "error", "-nostdin", "-y",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:a", "aac", str(voiceover)
            ], check=True, capture_output=True)

            contract = {
                "width": 64, "height": 64, "fps": 30, "duration": 1,
                "segments": [{"path": str(source), "duration": 1, "has_audio": False}],
                "audio_source": str(voiceover),
            }
            produce_app_preview.execute(contract, output, receipt, snapshot)
            probe = produce_app_preview.probe_media(output)
            audio = next((s for s in probe["streams"] if s.get("codec_type") == "audio"), None)
            self.assertIsNotNone(audio)
            self.assertEqual(audio["codec_name"], "aac")


class VideoEngineMultiLocaleTests(unittest.TestCase):
    def test_produce_preview_multi_locale_exports_per_locale_videos(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "en_capture.mov").write_bytes(b"en-dummy")
            (root / "zh_capture.mov").write_bytes(b"zh-dummy")
            (root / "creative.config.json").write_text(json.dumps({
                "project": {"locales": ["en-US", "zh-Hans"]},
                "targets": ["mac_16_10"],
                "previewVideo": {"enabled": True, "orientation": "landscape"},
                "localizations": {
                    "en-US": {"previewVideo": {"source": "en_capture.mov"}},
                    "zh-Hans": {"previewVideo": {"source": "zh_capture.mov"}},
                },
            }))
            executed_contracts = {}

            def fake_execute(contract, output, receipt, frames):
                executed_contracts[str(output)] = contract
                for p in (output, receipt, frames):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(b"mock-mp4-data")
                return {"output": {"probe": {}}, "tools": {}}

            fake_probe = {"streams": [{"codec_type": "video"}]}
            with mock.patch("video_engine.probe_video", return_value=fake_probe), \
                 mock.patch("produce_app_preview.execute", side_effect=fake_execute):
                result = video_engine.produce_preview_from_config(root)

            self.assertIsNotNone(result)
            self.assertIn("videos", result)
            self.assertEqual(set(result["videos"].keys()), {"en-US", "zh-Hans"})
            en_path = root / "artifacts/en-US/preview/app_preview.mp4"
            zh_path = root / "artifacts/zh-Hans/preview/app_preview.mp4"
            self.assertTrue(en_path.exists())
            self.assertTrue(zh_path.exists())
            self.assertIn(str(en_path), executed_contracts)
            self.assertIn(str(zh_path), executed_contracts)
