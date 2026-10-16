"""Unit tests for validator audio loudness gate and silence detection."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))

import validator


def make_mock_png(path: Path, width=2880, height=1800, color_type=2, with_trns=False):
    import struct, zlib
    path.parent.mkdir(parents=True, exist_ok=True)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 3)
    raw_scanline = b"\x00" + b"\xFF" * (width * channels)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    chunks = [
        chunk(b"IHDR", ihdr),
    ]
    if with_trns:
        chunks.append(chunk(b"tRNS", b"\x00\x00\x00\x00\x00\x00"))
    chunks.append(chunk(b"IDAT", zlib.compress(raw_scanline * height)))
    chunks.append(chunk(b"IEND", b""))
    data = b"\x89PNG\r\n\x1a\n" + b"".join(chunks)
    path.write_bytes(data)


class ValidatorAudioLoudnessTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.art_dir = self.root / "artifacts"
        self.art_dir.mkdir(parents=True, exist_ok=True)
        # Create screenshot
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png")
        # Create dummy source and preview video
        (self.root / "capture.mov").write_bytes(b"dummy-source")
        (self.art_dir / "preview").mkdir(parents=True, exist_ok=True)
        (self.art_dir / "preview/app_preview.mp4").write_bytes(b"dummy-mp4")
        self.base_config = {
            "project": {"id": "test", "locales": ["en-US"]},
            "targets": ["mac_16_10"],
            "cards": [{"id": "hero"}],
            "previewVideo": {
                "enabled": True,
                "source": "capture.mov",
                "orientation": "landscape",
                "width": 1920,
                "height": 1080,
                "duration": 20,
                "fps": 30,
            },
        }
        self.valid_probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
            ],
            "format": {"duration": "20.0"},
        }

    def tearDown(self):
        self.scratch.cleanup()

    def test_silent_audio_rejected_by_default(self):
        (self.root / "creative.config.json").write_text(json.dumps(self.base_config))
        with mock.patch("validator.inspect_video_file", return_value=self.valid_probe), \
             mock.patch("validator.inspect_audio_loudness", return_value={"mean_volume": -91.0, "max_volume": -85.0}):
            result = validator.run_validation(self.root)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("silent (< -80 dB)" in err for err in result["errors"]))

    def test_silent_audio_allowed_via_function_flag(self):
        (self.root / "creative.config.json").write_text(json.dumps(self.base_config))
        with mock.patch("validator.inspect_video_file", return_value=self.valid_probe), \
             mock.patch("validator.inspect_audio_loudness", return_value={"mean_volume": -91.0, "max_volume": -85.0}):
            result = validator.run_validation(self.root, allow_silent_audio=True)
            self.assertEqual(result["status"], "PASS")

    def test_silent_audio_allowed_via_preview_config(self):
        config = dict(self.base_config)
        config["previewVideo"]["allowSilentAudio"] = True
        (self.root / "creative.config.json").write_text(json.dumps(config))
        with mock.patch("validator.inspect_video_file", return_value=self.valid_probe), \
             mock.patch("validator.inspect_audio_loudness", return_value={"mean_volume": -91.0, "max_volume": -85.0}):
            result = validator.run_validation(self.root)
            self.assertEqual(result["status"], "PASS")

    def test_normal_volume_audio_passes(self):
        (self.root / "creative.config.json").write_text(json.dumps(self.base_config))
        with mock.patch("validator.inspect_video_file", return_value=self.valid_probe), \
             mock.patch("validator.inspect_audio_loudness", return_value={"mean_volume": -22.5, "max_volume": -3.1}):
            result = validator.run_validation(self.root)
            self.assertEqual(result["status"], "PASS")


class ValidatorMultiLocaleTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.art_dir = self.root / "artifacts"
        self.art_dir.mkdir(parents=True, exist_ok=True)
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png")
        make_mock_png(self.art_dir / "zh-Hans/mac_16_10/hero.png")
        (self.root / "inputs").mkdir(parents=True, exist_ok=True)
        (self.root / "inputs/en.mov").write_bytes(b"en-source")
        (self.root / "inputs/zh.mov").write_bytes(b"zh-source")
        (self.art_dir / "en-US/preview").mkdir(parents=True, exist_ok=True)
        (self.art_dir / "zh-Hans/preview").mkdir(parents=True, exist_ok=True)
        (self.art_dir / "en-US/preview/app_preview.mp4").write_bytes(b"en-mp4")
        (self.art_dir / "zh-Hans/preview/app_preview.mp4").write_bytes(b"zh-mp4")
        make_mock_png(self.art_dir / "en-US/preview/poster.png", 1920, 1080)
        make_mock_png(self.art_dir / "zh-Hans/preview/poster.png", 1920, 1080)
        self.config = {
            "project": {"id": "test", "locales": ["en-US", "zh-Hans"]},
            "targets": ["mac_16_10"],
            "cards": [{"id": "hero"}],
            "previewVideo": {
                "enabled": True,
                "orientation": "landscape",
                "posterRequired": True,
                "width": 1920,
                "height": 1080,
                "duration": 20,
                "fps": 30,
            },
            "localizations": {
                "en-US": {"previewVideo": {"source": "inputs/en.mov"}},
                "zh-Hans": {"previewVideo": {"source": "inputs/zh.mov"}},
            },
        }
        self.valid_probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000"},
            ],
            "format": {"duration": "20.0"},
        }

    def tearDown(self):
        self.scratch.cleanup()

    def test_multi_locale_previews_and_posters_pass(self):
        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        with mock.patch("validator.inspect_video_file", return_value=self.valid_probe), \
             mock.patch("validator.inspect_audio_loudness", return_value={"mean_volume": -20.0, "max_volume": -1.0}):
            result = validator.run_validation(self.root)
            self.assertEqual(result["status"], "PASS", result.get("errors"))
            self.assertIn("en-US/preview/app_preview.mp4", result["assets"])
            self.assertIn("zh-Hans/preview/app_preview.mp4", result["assets"])
            self.assertIn("en-US/preview/poster.png", result["assets"])
            self.assertIn("zh-Hans/preview/poster.png", result["assets"])

    def test_multi_locale_poster_dimension_mismatch_fails(self):
        # Mismatch zh-Hans poster dimensions
        make_mock_png(self.art_dir / "zh-Hans/preview/poster.png", 500, 500)
        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        with mock.patch("validator.inspect_video_file", return_value=self.valid_probe), \
             mock.patch("validator.inspect_audio_loudness", return_value={"mean_volume": -20.0, "max_volume": -1.0}):
            result = validator.run_validation(self.root)
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("Poster dimensions must match the validated App Preview: zh-Hans/preview/poster.png" in err
                                for err in result["errors"]))


class ValidatorAlphaChannelTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.art_dir = self.root / "artifacts"
        self.art_dir.mkdir(parents=True, exist_ok=True)
        self.config = {
            "project": {"id": "test", "locales": ["en-US"]},
            "targets": ["mac_16_10"],
            "cards": [{"id": "hero"}],
        }

    def tearDown(self):
        self.scratch.cleanup()

    def test_24bit_rgb_color_type_2_passes(self):
        # 24-bit RGB (color type 2) without alpha
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png", 2880, 1800, color_type=2)
        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        result = validator.run_validation(self.root)
        self.assertEqual(result["status"], "PASS", result.get("errors"))

    def test_rgba_color_type_6_fails_with_alpha_error(self):
        # Color type 6: RGBA with 8-bit alpha channel
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png", 2880, 1800, color_type=6)
        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        result = validator.run_validation(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("contains Alpha channel" in err for err in result["errors"]))

    def test_grayscale_alpha_color_type_4_fails_with_alpha_error(self):
        # Color type 4: Grayscale + Alpha (LA)
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png", 2880, 1800, color_type=4)
        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        result = validator.run_validation(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("contains Alpha channel" in err for err in result["errors"]))

    def test_trns_chunk_fails_with_alpha_error(self):
        # Color type 2 + tRNS transparency chunk
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png", 2880, 1800, color_type=2, with_trns=True)
        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        result = validator.run_validation(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("contains Alpha channel" in err for err in result["errors"]))

    def test_alpha_channel_allowed_with_explicit_exemption(self):
        # Explicit allowAlpha in config
        config = dict(self.config)
        config["project"]["allowAlpha"] = True
        make_mock_png(self.art_dir / "en-US/mac_16_10/hero.png", 2880, 1800, color_type=6)
        (self.root / "creative.config.json").write_text(json.dumps(config))
        result = validator.run_validation(self.root)
        self.assertEqual(result["status"], "PASS", result.get("errors"))

