import json
import struct
import tempfile
import unittest
import urllib.request
import zlib
from pathlib import Path
import sys

# Ensure plugin scripts are in sys.path
SCRIPTS_DIR = Path(__file__).parents[1] / "plugins/app-store-creative/scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import app_store_creative as cli
import export_engine
import studio_server
import validator


def create_mock_png(path: Path, width=1320, height=2868, has_alpha=False):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    color_type = 6 if has_alpha else 2  # 6=RGBA, 2=RGB
    bytes_per_pixel = 4 if has_alpha else 3
    raw_scanline = b"\x00" + b"\xFF" * (width * bytes_per_pixel)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_scanline * height))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(data)


class TestV2Workflow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.template_config = Path(__file__).parents[1] / "plugins/app-store-creative/assets/templates/creative.config.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_schema_and_template_config(self):
        self.assertTrue(self.template_config.exists())
        config_data = json.loads(self.template_config.read_text())
        self.assertIn("project", config_data)
        self.assertIn("targets", config_data)
        self.assertIn("cards", config_data)
        self.assertGreaterEqual(len(config_data["cards"]), 1)

    def test_target_specs_completeness(self):
        # Verify Apple required sizes are defined
        for key in ["iphone_6_9", "iphone_6_7", "iphone_6_5", "ipad_13", "mac_16_10"]:
            self.assertIn(key, export_engine.TARGET_SPECS)
            spec = export_engine.TARGET_SPECS[key]
            self.assertGreater(spec["width"], 0)
            self.assertGreater(spec["height"], 0)

    def test_validator_detects_valid_and_invalid_assets(self):
        artifacts = self.root / "artifacts"
        valid_png = artifacts / "en-US/iphone_6_9/01-hero.png"
        create_mock_png(valid_png, width=1320, height=2868, has_alpha=False)

        res = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
            write_lockfile=True,
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["assets_count"], 1)

        # Check that .creative/release-lock.json was written
        lock_file = self.root / ".creative/release-lock.json"
        self.assertTrue(lock_file.exists())
        lock_data = json.loads(lock_file.read_text())
        self.assertEqual(lock_data["status"], "PASS")
        self.assertIn("en-US/iphone_6_9/01-hero.png", lock_data["assets"])

        # Now introduce an invalid asset (wrong dimension)
        invalid_dim_png = artifacts / "en-US/iphone_6_9/02-bad.png"
        create_mock_png(invalid_dim_png, width=800, height=600, has_alpha=False)

        res_bad = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
            write_lockfile=False,
        )
        self.assertEqual(res_bad["status"], "FAIL")
        self.assertTrue(any("Dimension mismatch" in err for err in res_bad["errors"]))

    def test_validator_supports_target_name_aliases(self):
        artifacts = self.root / "artifacts"
        # Directory named iphone-6.9 instead of iphone_6_9
        aliased_png = artifacts / "en-US/iphone-6.9/01-hero.png"
        create_mock_png(aliased_png, width=1320, height=2868, has_alpha=False)

        res = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
            write_lockfile=False,
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["errors"]), 0)

    def test_path_traversal_protection(self):
        base_dir = self.root / "project"
        base_dir.mkdir(parents=True)
        secret_file = self.root / "secret.txt"
        secret_file.write_text("SUPER_SECRET")

        # is_safe_child should return False for escaped path
        escaped_candidate = base_dir / "../secret.txt"
        self.assertFalse(studio_server.is_safe_child(base_dir, escaped_candidate))

        # Safe child should return True
        safe_candidate = base_dir / "valid.png"
        safe_candidate.write_text("DATA")
        self.assertTrue(studio_server.is_safe_child(base_dir, safe_candidate))

    def test_free_port_discovery(self):
        port = export_engine.find_free_port(3100)
        self.assertGreaterEqual(port, 3100)
        self.assertLess(port, 3150)

    def test_publish_dry_run_and_gate(self):
        # 1. Publish without release lock fails
        parser = cli.build_parser()
        args = parser.parse_args(["publish", "--repo", str(self.root)])
        with self.assertRaises(Exception):
            cli.run(args)

        # 2. Write valid release-lock.json
        lock_dir = self.root / ".creative"
        lock_dir.mkdir(parents=True)
        lock_file = lock_dir / "release-lock.json"
        lock_file.write_text(json.dumps({"status": "PASS", "assets_count": 3}))

        # 3. Dry-run publish succeeds
        res_dry = cli.run(args)
        self.assertEqual(res_dry["mode"], "dry-run")
        self.assertTrue(res_dry["ready_for_upload"])
        self.assertEqual(res_dry["assets_count"], 3)

    def test_verify_cli_returns_error_code_on_failure(self):
        artifacts = self.root / "artifacts"
        bad_png = artifacts / "en-US/iphone_6_9/bad.png"
        create_mock_png(bad_png, width=100, height=200)

        cfg_file = self.root / "creative.config.json"
        cfg_file.write_text(self.template_config.read_text())

        exit_code = cli.main(["verify", "--repo", str(self.root), "--output-dir", str(artifacts)])
        self.assertEqual(exit_code, 2)

    def test_trns_alpha_detection_in_fallback_reader(self):
        # Create a PNG with a tRNS chunk
        png_path = self.root / "trns_sample.png"
        raw_data = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x03\x00\x00\x00" + b"\x00\x00\x00\x06tRNS\x00\x01\x02\x03\x04\x05"
        png_path.write_bytes(raw_data)

        # Force pure python path by temporarily disabling sips check
        import shutil
        original_which = shutil.which
        shutil.which = lambda cmd: None if cmd == "sips" else original_which(cmd)
        try:
            _, _, has_alpha = validator.read_image_meta(png_path)
            self.assertTrue(has_alpha)
        finally:
            shutil.which = original_which

    def test_google_play_target_specs(self):
        gp_keys = ["google_play_phone", "google_play_tablet_7", "google_play_tablet_10", "google_play_feature_graphic"]
        for key in gp_keys:
            self.assertIn(key, export_engine.TARGET_SPECS)
            spec = export_engine.TARGET_SPECS[key]
            self.assertGreater(spec["width"], 0)
            self.assertGreater(spec["height"], 0)
        self.assertEqual(export_engine.TARGET_SPECS["google_play_feature_graphic"]["width"], 1024)
        self.assertEqual(export_engine.TARGET_SPECS["google_play_feature_graphic"]["height"], 500)
        self.assertEqual(export_engine.TARGET_SPECS["google_play_phone"]["width"], 1080)
        self.assertEqual(export_engine.TARGET_SPECS["google_play_phone"]["height"], 2400)

    def test_validator_supports_google_play_targets(self):
        artifacts = self.root / "artifacts"
        # 1. Feature Graphic (1024x500)
        fg_png = artifacts / "en-US/google_play_feature_graphic/banner.png"
        create_mock_png(fg_png, width=1024, height=500, has_alpha=False)

        # 2. Google Play Phone (1080x2400)
        phone_png = artifacts / "en-US/google_play_phone/01-hero.png"
        create_mock_png(phone_png, width=1080, height=2400, has_alpha=False)

        res = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
            write_lockfile=True,
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["assets_count"], 2)

    def test_studio_server_post_config_and_backup(self):
        cfg_file = self.root / "creative.config.json"
        cfg_file.write_text(self.template_config.read_text())

        with export_engine.LocalServerContext(self.root, cfg_file) as ctx:
            # 1. Fetch current config via GET /api/config
            get_req = urllib.request.Request(f"http://127.0.0.1:{ctx.port}/api/config")
            with urllib.request.urlopen(get_req) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode())
                self.assertIn("cards", data)

            # 2. Update config via POST /api/config
            data["cards"][0]["headline"] = "Updated Headline From Test"
            post_bytes = json.dumps(data).encode()
            post_req = urllib.request.Request(
                f"http://127.0.0.1:{ctx.port}/api/config",
                data=post_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(post_req) as resp:
                self.assertEqual(resp.status, 200)
                res_body = json.loads(resp.read().decode())
                self.assertTrue(res_body["ok"])

            # 3. Verify disk file was updated
            saved_disk = json.loads(cfg_file.read_text())
            self.assertEqual(saved_disk["cards"][0]["headline"], "Updated Headline From Test")

            # 4. Verify backup was created in .creative/backups/
            backup_dir = self.root / ".creative/backups"
            self.assertTrue(backup_dir.exists())
            backups = list(backup_dir.glob("creative.config.*.json"))
            self.assertGreaterEqual(len(backups), 1)

            # 5. Verify server gracefully handles invalid/malformed JSON
            invalid_post = urllib.request.Request(
                f"http://127.0.0.1:{ctx.port}/api/config",
                data=b"NOT_A_JSON_STRING",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(invalid_post)
            self.assertEqual(cm.exception.code, 400)

    def test_validator_handles_corrupted_png(self):
        artifacts = self.root / "artifacts"
        # 1. Zero-byte file
        zero_png = artifacts / "en-US/iphone_6_9/zero.png"
        zero_png.parent.mkdir(parents=True, exist_ok=True)
        zero_png.write_bytes(b"")

        # 2. Corrupted magic header
        garbage_png = artifacts / "en-US/iphone_6_9/garbage.png"
        garbage_png.write_bytes(b"NOT_A_PNG_HEADER_DATA")

        res = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
            write_lockfile=False,
        )
        self.assertEqual(res["status"], "FAIL")
        self.assertGreaterEqual(len(res["errors"]), 2)
        self.assertTrue(any("zero.png" in err for err in res["errors"]))
        self.assertTrue(any("garbage.png" in err for err in res["errors"]))

    def test_video_engine_dimensions_resolution_and_overrides(self):
        import video_engine

        # Case 1: Default iPhone portrait (886x1920)
        cfg_iphone_portrait = self.root / "cfg_iphone_portrait.json"
        cfg_iphone_portrait.write_text(json.dumps({
            "targets": ["iphone_6_9"],
            "previewVideo": {"enabled": True, "source": "dummy.mov", "orientation": "portrait"}
        }))
        # Case 2: Default iPhone landscape (1920x886)
        cfg_iphone_landscape = self.root / "cfg_iphone_landscape.json"
        cfg_iphone_landscape.write_text(json.dumps({
            "targets": ["iphone_6_9"],
            "previewVideo": {"enabled": True, "source": "dummy.mov", "orientation": "landscape"}
        }))
        # Case 3: Default Mac desktop target (1920x1080 - 16:9 Mac App Store standard)
        cfg_mac_default = self.root / "cfg_mac_default.json"
        cfg_mac_default.write_text(json.dumps({
            "targets": ["mac_16_10"],
            "previewVideo": {"enabled": True, "source": "dummy.mov", "orientation": "landscape"}
        }))
        # Case 4: Explicit width and height configuration overrides
        cfg_custom = self.root / "cfg_custom.json"
        cfg_custom.write_text(json.dumps({
            "targets": ["iphone_6_9"],
            "previewVideo": {"enabled": True, "source": "dummy.mov", "width": 1080, "height": 1920}
        }))

        # Mock dummy file
        dummy_mov = self.root / "dummy.mov"
        dummy_mov.write_bytes(b"dummy")

        def fake_run(cmd, *args, **kwargs):
            # Touch target output file so .stat() succeeds
            out_file = self.root / "artifacts/preview/app_preview.mp4"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"mock_mp4")
            return unittest.mock.MagicMock()

        # Test contract construction via mocking subprocess and produce_app_preview
        with unittest.mock.patch("video_engine.build_command") as mock_build, \
             unittest.mock.patch("video_engine.validate_output") as mock_validate, \
             unittest.mock.patch("subprocess.run", side_effect=fake_run), \
             unittest.mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"):

            mock_validate.return_value = {"streams": []}

            # 1. iPhone Portrait
            video_engine.produce_preview_from_config(self.root, config_path=cfg_iphone_portrait)
            contract_iphone_p = mock_build.call_args[0][0]
            self.assertEqual(contract_iphone_p["width"], 886)
            self.assertEqual(contract_iphone_p["height"], 1920)

            # 2. iPhone Landscape
            video_engine.produce_preview_from_config(self.root, config_path=cfg_iphone_landscape)
            contract_iphone_l = mock_build.call_args[0][0]
            self.assertEqual(contract_iphone_l["width"], 1920)
            self.assertEqual(contract_iphone_l["height"], 886)

            # 3. Mac Landscape -> Strict 16:9 (1920x1080)
            video_engine.produce_preview_from_config(self.root, config_path=cfg_mac_default)
            contract_mac = mock_build.call_args[0][0]
            self.assertEqual(contract_mac["width"], 1920)
            self.assertEqual(contract_mac["height"], 1080)

            # 4. Custom dimensions override
            video_engine.produce_preview_from_config(self.root, config_path=cfg_custom)
            contract_custom = mock_build.call_args[0][0]
            self.assertEqual(contract_custom["width"], 1080)
            self.assertEqual(contract_custom["height"], 1920)


if __name__ == "__main__":
    unittest.main()
