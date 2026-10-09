import json
import struct
import tempfile
import unittest
from unittest import mock
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
        self.template_config = self.root / "creative.config.json"
        self.template_config.write_text(json.dumps({
            "project": {"id": "workflow-fixture", "locales": ["en-US"]}, "targets": ["iphone_6_9"],
            "cards": [{"id": "01-hero"}]}))

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
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["assets_count"], 1)

        self.assertFalse((self.root / ".creative").exists())
        self.assertIn("en-US/iphone_6_9/01-hero.png", res["assets"])

        # Now introduce an invalid asset (wrong dimension)
        invalid_dim_png = artifacts / "en-US/iphone_6_9/02-bad.png"
        create_mock_png(invalid_dim_png, width=800, height=600, has_alpha=False)

        res_bad = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
        )
        self.assertEqual(res_bad["status"], "FAIL")
        self.assertTrue(any("Dimension mismatch" in err for err in res_bad["errors"]))

    def test_validator_supports_target_name_aliases(self):
        artifacts = self.root / "artifacts"
        config = json.loads(self.template_config.read_text())
        config["targets"] = ["iphone-6.9"]
        self.template_config.write_text(json.dumps(config))
        # Directory named iphone-6.9 instead of iphone_6_9
        aliased_png = artifacts / "en-US/iphone-6.9/01-hero.png"
        create_mock_png(aliased_png, width=1320, height=2868, has_alpha=False)

        res = validator.run_validation(
            repo_root=self.root,
            config_path=self.template_config,
            artifacts_dir=artifacts,
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

    def test_trns_alpha_detection_in_fallback_reader(self):
        png_path = self.root / "trns_sample.png"
        create_mock_png(png_path, 10, 10)
        data = png_path.read_bytes()
        payload = struct.pack(">HHH", 255, 255, 255)
        transparency = (struct.pack(">I", len(payload)) + b"tRNS" + payload
                        + struct.pack(">I", zlib.crc32(b"tRNS" + payload) & 0xFFFFFFFF))
        png_path.write_bytes(data[:33] + transparency + data[33:])
        self.assertEqual(validator.read_image_meta(png_path), (10, 10, True))

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
        self.template_config.write_text(json.dumps({
            "project": {"locales": ["en-US"]}, "targets": ["google_play_phone"],
            "cards": [{"id": "01-hero"}]}))
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
        )
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(res["assets_count"], 2)

    def test_studio_server_post_config_and_backup(self):
        cfg_file = self.root / "creative.config.json"
        cfg_file.write_text(self.template_config.read_text())

        original_config = cfg_file.read_bytes()
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

            # 4. Verify the original bytes have a managed configuration backup.
            import artifact_lifecycle
            core = artifact_lifecycle.Lifecycle(self.root, json.loads(self.template_config.read_text()))
            backups = [core._read('artifacts', p.stem) for p in (core.paths.workspace / 'records/artifacts').glob('*.json')]
            backups = [record for record in backups if record['role'] == 'configuration']
            self.assertEqual(len(backups), 1)
            self.assertEqual(core.object_path(backups[0]['sha256']).read_bytes(), original_config)
            self.assertFalse((self.root / '.creative/backups').exists())

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

        with unittest.mock.patch("produce_app_preview.execute") as executor:
            executor.return_value = {"output": {"probe": {"streams": []}}}

            # 1. iPhone Portrait
            video_engine.produce_preview_from_config(self.root, config_path=cfg_iphone_portrait)
            contract_iphone_p = executor.call_args[0][0]
            self.assertEqual(contract_iphone_p["width"], 886)
            self.assertEqual(contract_iphone_p["height"], 1920)

            # 2. iPhone Landscape
            video_engine.produce_preview_from_config(self.root, config_path=cfg_iphone_landscape)
            contract_iphone_l = executor.call_args[0][0]
            self.assertEqual(contract_iphone_l["width"], 1920)
            self.assertEqual(contract_iphone_l["height"], 886)

            # 3. Mac Landscape -> Strict 16:9 (1920x1080)
            video_engine.produce_preview_from_config(self.root, config_path=cfg_mac_default)
            contract_mac = executor.call_args[0][0]
            self.assertEqual(contract_mac["width"], 1920)
            self.assertEqual(contract_mac["height"], 1080)

            # 4. Custom dimensions override
            video_engine.produce_preview_from_config(self.root, config_path=cfg_custom)
            contract_custom = executor.call_args[0][0]
            self.assertEqual(contract_custom["width"], 1080)
            self.assertEqual(contract_custom["height"], 1920)


if __name__ == "__main__":
    unittest.main()
