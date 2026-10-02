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

    def test_missing_declared_card_fails(self):
        self.config["cards"].append({"id": "missing"})
        self.save()
        self.assertEqual(self.verify()["status"], "FAIL")

    def test_empty_artifacts_replaces_old_pass_lock(self):
        self.verify()
        (self.art / "en-US/mac_16_10/hero.png").unlink()
        self.assertEqual(self.verify()["status"], "FAIL")
        lock = json.loads((self.root / ".creative/release-lock.json").read_text())
        self.assertEqual(lock["status"], "FAIL")

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

    def test_handoff_is_local_ordered_and_never_uploaded(self):
        self.verify()
        args = cli.build_parser().parse_args(["publish", "--repo", str(self.root), "--confirm"])
        result = cli.run(args)
        self.assertFalse(result["uploaded"])
        self.assertEqual(result["status"], "awaiting_asc")
        package = json.loads(Path(result["handoff_path"]).read_text())
        self.assertEqual(package["executor"], "official-asc-plugin")
        self.assertEqual(package["screenshots"][0]["order"], 1)
        self.assertEqual(package["screenshots"][0]["locale"], "en-US")
        self.assertTrue(package["upload_approval_required"])

    def test_changed_asset_blocks_handoff(self):
        self.verify()
        (self.art / "en-US/mac_16_10/hero.png").write_bytes(b"changed")
        args = cli.build_parser().parse_args(["publish", "--repo", str(self.root)])
        with self.assertRaises(Exception):
            cli.run(args)

    def test_changed_config_blocks_handoff(self):
        self.verify()
        self.config["cards"][0]["headline"] = "Changed"
        self.save()
        args = cli.build_parser().parse_args(["publish", "--repo", str(self.root)])
        with self.assertRaises(Exception):
            cli.run(args)

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

    def test_changed_recording_blocks_handoff(self):
        source = self.root / "recording.mov"
        source.write_bytes(b"original")
        self.config["previewVideo"] = {"enabled": True, "source": source.name}
        self.save()
        video = self.art / "preview/app_preview.mp4"
        video.parent.mkdir()
        video.write_bytes(b"fixture")
        probe = {"format": {"duration": "20"}, "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920,
             "height": 1080, "r_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac"}]}
        with mock.patch("validator.inspect_video_file", return_value=probe):
            self.assertEqual(self.verify()["status"], "PASS")
        source.write_bytes(b"changed")
        args = cli.build_parser().parse_args(["publish", "--repo", str(self.root)])
        with self.assertRaises(ValueError):
            cli.run(args)

    def test_doctor_rejects_unsupported_python(self):
        args = cli.build_parser().parse_args(["doctor", "--repo", str(self.root)])
        with mock.patch("creative_workflow.sys.version_info", (3, 9, 6)):
            self.assertEqual(cli.run(args)["status"], "FAIL")

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
