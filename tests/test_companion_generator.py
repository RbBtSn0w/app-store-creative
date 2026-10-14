import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import app_store_creative as cli
import companion_generator


class TestCompanionGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_path = self.root / "creative.config.json"
        self.config_data = {
            "project": {
                "id": "test-app",
                "name": "Test Application",
                "locales": ["en-US", "zh-Hans"],
                "defaultLocale": "en-US",
            },
            "targets": ["mac_16_10"],
            "cards": [
                {
                    "id": "01-hero",
                    "headline": "Hero Title",
                    "subheadline": "Hero Subtitle",
                    "layout": "mac_native_hero",
                    "deviceOffset": {
                        "rotateX": 4,
                        "rotateY": 0,
                        "rotate": 0,
                        "scale": 1.03,
                        "x": 0,
                        "y": 25,
                    },
                },
                {
                    "id": "02-features",
                    "headline": "Feature Title",
                    "subheadline": "Feature Subtitle",
                    "layout": "mac_native_left",
                    "deviceOffset": {
                        "rotateX": 4,
                        "rotateY": 8,
                        "rotate": -2,
                        "scale": 1.02,
                        "x": 0,
                        "y": 0,
                    },
                },
            ],
            "localizations": {
                "zh-Hans": {
                    "01-hero": {
                        "headline": "中文主标题",
                        "subheadline": "中文副标题",
                    }
                }
            },
        }
        self.config_path.write_text(json.dumps(self.config_data, indent=2))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_companion_default_output(self):
        result = companion_generator.generate_companion(repo_root=self.root)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["cards_count"], 2)
        self.assertEqual(result["target"], "mac_16_10")
        self.assertEqual(result["locale"], "en-US")

        out_file = self.root / ".creative" / "companion.html"
        self.assertTrue(out_file.is_file())

        content = out_file.read_text(encoding="utf-8")
        self.assertIn("Test Application", content)
        self.assertIn("ZERO-SERVER COMPANION", content)
        self.assertIn("downloadDirectivesJson", content)
        self.assertIn("Hero Title", content)
        self.assertIn("data:image/svg+xml;base64,", content)

    def test_generate_companion_custom_output_and_locale(self):
        custom_out = self.root / "artifacts" / "review.html"
        result = companion_generator.generate_companion(
            repo_root=self.root,
            output_path=custom_out,
            locale="zh-Hans",
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["locale"], "zh-Hans")
        self.assertTrue(custom_out.is_file())

        content = custom_out.read_text(encoding="utf-8")
        self.assertIn("中文主标题", content)
        self.assertIn("中文副标题", content)

    def test_cli_companion_subcommand(self):
        custom_out = self.root / "out_companion.html"
        exit_code = cli.main([
            "companion",
            "--repo", str(self.root),
            "--config", str(self.config_path),
            "--output", str(custom_out),
            "--target", "mac_16_10",
            "--locale", "en-US",
        ])
        self.assertEqual(exit_code, 0)
        self.assertTrue(custom_out.is_file())
        self.assertIn("Hero Title", custom_out.read_text(encoding="utf-8"))

    def test_empty_cards_rejected(self):
        empty_config = dict(self.config_data)
        empty_config["cards"] = []
        cfg_path = self.root / "empty.config.json"
        cfg_path.write_text(json.dumps(empty_config))
        with self.assertRaises(ValueError) as ctx:
            companion_generator.generate_companion(repo_root=self.root, config_path=cfg_path)
        self.assertIn("cards", str(ctx.exception))

    def test_script_tag_escaping(self):
        xss_config = dict(self.config_data)
        xss_config["cards"] = [
            {
                "id": "01-xss",
                "headline": "Evil</script><script>alert(1)</script>",
                "subheadline": "Subtitle",
                "layout": "mac_native_hero",
            }
        ]
        cfg_path = self.root / "xss.config.json"
        cfg_path.write_text(json.dumps(xss_config))
        out_path = self.root / "xss.html"
        result = companion_generator.generate_companion(repo_root=self.root, config_path=cfg_path, output_path=out_path)
        self.assertEqual(result["status"], "ok")
        html_out = out_path.read_text(encoding="utf-8")
        # Ensure </script> is escaped inside the embedded JSON
        self.assertNotIn("Evil</script>", html_out)
        self.assertIn("Evil<\\/script>", html_out)

    def test_generate_companion_omitted_targets_defaults_to_iphone_6_9(self):
        # When targets is not declared, match studio_contract default iphone_6_9
        no_targets_config = dict(self.config_data)
        del no_targets_config["targets"]
        cfg_path = self.root / "no_targets.config.json"
        cfg_path.write_text(json.dumps(no_targets_config))
        result = companion_generator.generate_companion(repo_root=self.root, config_path=cfg_path)
        self.assertEqual(result["target"], "iphone_6_9")

    def test_generate_companion_is_offline_and_uses_offset_ids(self):
        result = companion_generator.generate_companion(repo_root=self.root)
        self.assertEqual(result["status"], "ok")
        out_file = self.root / ".creative" / "companion.html"
        content = out_file.read_text(encoding="utf-8")

        # Zero-server offline requirement: no remote scripts
        self.assertNotIn("tailwindcss.min.js", content)
        self.assertNotIn("gstatic.com", content)

        # Unique offset IDs to prevent yaw/y ambiguity
        self.assertIn('id="slider-offset-y"', content)
        self.assertIn('id="val-offset-y"', content)
        self.assertIn('id="slider-yaw"', content)
        self.assertIn('document.getElementById(\'slider-offset-y\')', content)

        # Safe nav building via createElement and textContent
        self.assertIn("headlineSpan.textContent = c.headline;", content)


if __name__ == "__main__":
    unittest.main()
