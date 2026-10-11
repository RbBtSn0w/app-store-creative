"""Regression coverage for complete artifacts and truthful ASC handoffs."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from test_v2_workflow import cli, validator, create_mock_png
import video_engine


class ArtifactHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = {"project": {"locales": ["en-US"]}, "targets": ["mac_16_10"],
                       "cards": [{"id": "hero"}]}
        self.cfg = self.root / "creative.config.json"
        self.save()
        self.art = self.root / "artifacts"
        create_mock_png(self.art / "en-US/mac_16_10/hero.png", 2880, 1800)

    def save(self):
        self.cfg.write_text(json.dumps(self.config))

    def verify(self):
        return validator.run_validation(self.root)

    def test_media_probe_does_not_write_release_authority(self):
        self.assertEqual(self.verify()["status"], "PASS")
        self.assertFalse((self.root / ".creative").exists())

    def test_missing_declared_card_fails(self):
        self.config["cards"].append({"id": "missing"})
        self.save()
        self.assertEqual(self.verify()["status"], "FAIL")

    def test_empty_artifacts_cannot_reuse_previous_pass(self):
        self.assertEqual(self.verify()["status"], "PASS")
        (self.art / "en-US/mac_16_10/hero.png").unlink()
        self.assertEqual(self.verify()["status"], "FAIL")
        self.assertFalse((self.root / ".creative").exists())

    def test_enabled_preview_requires_source_and_output(self):
        self.config["previewVideo"] = {"enabled": True, "source": "missing.mov"}
        self.save()
        self.assertEqual(self.verify()["status"], "FAIL")
        with self.assertRaises((ValueError, FileNotFoundError)):
            video_engine.produce_preview_from_config(self.root)

    def test_unprobeable_video_fails(self):
        video = self.art / "preview/app_preview.mp4"
        video.parent.mkdir()
        video.write_bytes(b"invalid")
        with mock.patch("validator.shutil.which", return_value=None):
            self.assertEqual(self.verify()["status"], "FAIL")

    def test_video_dimensions_and_fps_are_verified(self):
        video = self.art / "preview/app_preview.mp4"
        video.parent.mkdir()
        video.write_bytes(b"fixture")
        probe = {"format": {"duration": "20"}, "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920,
             "height": 1080, "r_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac"}]}
        with mock.patch("validator.inspect_video_file", return_value=probe):
            self.assertEqual(self.verify()["status"], "PASS")
            probe["streams"][0]["width"] = 100
            self.assertEqual(self.verify()["status"], "FAIL")
            probe["streams"][0]["width"] = 1920
            probe["streams"][0]["r_frame_rate"] = "60/1"
            self.assertEqual(self.verify()["status"], "FAIL")

    def test_legacy_cli_commands_are_not_available(self):
        import contextlib
        import io
        commands = ("doctor", "init", "plan", "status", "claim", "invalidate",
                    "complete", "approve", "promote", "upload-plan", "upload", "audit", "upgrade", "verify", "publish")
        for command in commands:
            with self.subTest(command=command), contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as failure:
                    cli.build_parser().parse_args([command])
                self.assertEqual(failure.exception.code, 2)
                self.assertIn("invalid choice", errors.getvalue())

    def test_preview_locale_scope_keeps_english_video_out_of_chinese_slot(self):
        config = {"project": {"locales": ["en-US", "zh-Hans"]},
                  "previewVideo": {"locales": ["en-US"]}}
        self.assertEqual(validator.preview_locales(config), ["en-US"])
        config["previewVideo"]["locales"] = ["ja"]
        with self.assertRaises(ValueError):
            validator.preview_locales(config)
        config["previewVideo"]["locales"] = []
        with self.assertRaises(ValueError):
            validator.preview_locales(config)
