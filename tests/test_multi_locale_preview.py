"""Tests for multi-locale App Preview matrix generation, validation, and delivery sealing."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import artifact_lifecycle as lifecycle
import validator
from test_v2_workflow import create_mock_png


class MultiLocalePreviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

        (self.root / "inputs").mkdir(parents=True, exist_ok=True)
        (self.root / "inputs/en_preview.mov").write_bytes(b"en-mov-source")
        (self.root / "inputs/zh_preview.mov").write_bytes(b"zh-mov-source")

        self.config = {
            "project": {
                "id": "demo",
                "name": "Demo",
                "bundleId": "example.demo",
                "locales": ["en-US", "zh-Hans"],
            },
            "targets": ["mac_16_10"],
            "cards": [{"id": "hero", "screenshot": "source.png"}],
            "archivePolicy": {"schema_version": 1, "mediaMode": "git"},
            "artifactPolicy": {"schema_version": 1, "mediaBudgetBytes": 1073741824},
            "previewVideo": {
                "enabled": True,
                "orientation": "landscape",
                "posterRequired": True,
                "allowSilentAudio": True,
                "duration": 20,
                "fps": 30,
            },
            "localizations": {
                "en-US": {"previewVideo": {"source": "inputs/en_preview.mov"}},
                "zh-Hans": {"previewVideo": {"source": "inputs/zh_preview.mov"}},
            },
        }
        self.store = lifecycle.Lifecycle(self.root, self.config)
        self.run = self.store.start_run({"version": "1.0", "platform": "MAC_OS"})

        # Register sources and screenshot outputs
        attempt = self.store.start_attempt(self.run["id"], "render", "agent")
        source = self.root / "source.png"
        create_mock_png(source, 2880, 1800)
        self.input = self.store.register(attempt["id"], source, "source", logical_path="source.png")

        en_mov = self.root / "inputs/en_preview.mov"
        zh_mov = self.root / "inputs/zh_preview.mov"
        self.input_en_mov = self.store.register(attempt["id"], en_mov, "source", logical_path="inputs/en_preview.mov")
        self.input_zh_mov = self.store.register(attempt["id"], zh_mov, "source", logical_path="inputs/zh_preview.mov")

        self.shot_en = self.store.register(
            attempt["id"], source, "screenshot", inputs=[self.input["id"]],
            logical_path="en-US/mac_16_10/hero.png"
        )
        self.shot_zh = self.store.register(
            attempt["id"], source, "screenshot", inputs=[self.input["id"]],
            logical_path="zh-Hans/mac_16_10/hero.png"
        )

        # Create mock mp4s and posters
        en_mp4 = self.root / "mock_en.mp4"
        zh_mp4 = self.root / "mock_zh.mp4"
        en_mp4.write_bytes(b"mock-en-mp4-stream-data")
        zh_mp4.write_bytes(b"mock-zh-mp4-stream-data")

        en_poster = self.root / "mock_en_poster.png"
        zh_poster = self.root / "mock_zh_poster.png"
        create_mock_png(en_poster, 1920, 1080)
        create_mock_png(zh_poster, 1920, 1080)

        self.preview_en = self.store.register(
            attempt["id"], en_mp4, "preview", inputs=[self.input_en_mov["id"]],
            logical_path="en-US/preview/app_preview.mp4"
        )
        self.preview_zh = self.store.register(
            attempt["id"], zh_mp4, "preview", inputs=[self.input_zh_mov["id"]],
            logical_path="zh-Hans/preview/app_preview.mp4"
        )

        self.poster_en = self.store.register(
            attempt["id"], en_poster, "poster", inputs=[self.preview_en["id"]],
            logical_path="en-US/preview/poster.png"
        )
        self.poster_zh = self.store.register(
            attempt["id"], zh_poster, "poster", inputs=[self.preview_zh["id"]],
            logical_path="zh-Hans/preview/poster.png"
        )
        self.store.finish_attempt(attempt["id"], "succeeded")

    def _mock_video_probe(self):
        fake_probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "20.0"},
        }
        return mock.patch("validator.inspect_video_file", return_value=fake_probe)

    def test_multi_locale_candidate_validation_and_delivery_sealing(self):
        artifacts = [
            self.shot_en["id"], self.shot_zh["id"],
            self.preview_en["id"], self.preview_zh["id"],
            self.poster_en["id"], self.poster_zh["id"],
        ]
        candidate = self.store.select(self.run["id"], artifacts)

        with self._mock_video_probe():
            validation = self.store.validate_candidate(candidate["id"])
            self.assertEqual(validation["status"], "PASS", validation.get("errors"))

        approval = self.store.approve_design(candidate["id"], validation["id"], "owner", "human:design-ok")
        delivery = self.store.seal(candidate["id"], validation["id"], approval["id"])

        package = self.store.delivery_path(delivery)
        manifest = json.loads((package / "manifest.json").read_text())

        asset_paths = [a["path"] for a in manifest["assets"]]
        self.assertIn("media/en-US/preview/app_preview.mp4", asset_paths)
        self.assertIn("media/zh-Hans/preview/app_preview.mp4", asset_paths)
        self.assertIn("media/en-US/preview/poster.png", asset_paths)
        self.assertIn("media/zh-Hans/preview/poster.png", asset_paths)

        # Verify distinct sha256 for the distinct previews
        en_asset = next(a for a in manifest["assets"] if a["path"] == "media/en-US/preview/app_preview.mp4")
        zh_asset = next(a for a in manifest["assets"] if a["path"] == "media/zh-Hans/preview/app_preview.mp4")
        self.assertNotEqual(en_asset["sha256"], zh_asset["sha256"])

    def test_multi_locale_missing_locale_preview_fails_validation(self):
        # Omit zh-Hans preview and poster
        artifacts = [
            self.shot_en["id"], self.shot_zh["id"],
            self.preview_en["id"],
            self.poster_en["id"],
        ]
        candidate = self.store.select(self.run["id"], artifacts)

        with self._mock_video_probe():
            validation = self.store.validate_candidate(candidate["id"])
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(any("Missing declared output: zh-Hans/preview/app_preview.mp4" in err for err in validation["errors"]))

    def test_multi_locale_poster_bound_to_cross_locale_preview_fails_validation(self):
        # Register a poster for zh that erroneously points to en preview
        attempt = self.store.start_attempt(self.run["id"], "poster", "agent")
        zh_poster = self.root / "mock_zh_poster.png"
        bad_poster = self.store.register(
            attempt["id"], zh_poster, "poster", inputs=[self.preview_en["id"]],
            logical_path="zh-Hans/preview/poster.png"
        )
        self.store.finish_attempt(attempt["id"], "succeeded")

        artifacts = [
            self.shot_en["id"], self.shot_zh["id"],
            self.preview_en["id"], self.preview_zh["id"],
            self.poster_en["id"], bad_poster["id"],
        ]
        candidate = self.store.select(self.run["id"], artifacts)

        with self._mock_video_probe():
            validation = self.store.validate_candidate(candidate["id"])
            self.assertEqual(validation["status"], "FAIL")
            self.assertTrue(any("Poster must reference the selected preview: zh-Hans/preview/poster.png" in err for err in validation["errors"]))

    def test_locale_path_traversal_is_rejected(self):
        import video_engine
        bad_config = json.loads(json.dumps(self.config))
        bad_config["project"]["locales"] = ["../../outside"]
        bad_config["localizations"] = {
            "../../outside": {"previewVideo": {"source": "inputs/en_preview.mov"}}
        }
        cfg_file = self.root / "bad_creative.config.json"
        cfg_file.write_text(json.dumps(bad_config))
        with self.assertRaisesRegex(ValueError, "escapes output directory"):
            video_engine.produce_preview_from_config(self.root, cfg_file, output_dir=self.root / "artifacts")


if __name__ == "__main__":
    unittest.main()
