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


if __name__ == "__main__":
    unittest.main()
