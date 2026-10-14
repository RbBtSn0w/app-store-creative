import json
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock

SCRIPTS_DIR = Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import app_store_creative as cli
import apply_critique


class TestApplyCritique(unittest.TestCase):
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
                    "headline": "Original Headline",
                    "subheadline": "Original Subheadline",
                    "layout": "mac_native_hero",
                    "deviceOffset": {
                        "rotateX": 0,
                        "rotateY": 0,
                        "rotate": 0,
                        "scale": 1.0,
                        "x": 0,
                        "y": 0,
                    },
                },
                {
                    "id": "02-features",
                    "headline": "Features Title",
                    "subheadline": "Features Subtitle",
                    "layout": "mac_native_left",
                    "deviceOffset": {
                        "rotateX": 0,
                        "rotateY": 0,
                        "rotate": 0,
                        "scale": 1.0,
                        "x": 0,
                        "y": 0,
                    },
                },
            ],
            "localizations": {
                "zh-Hans": {
                    "01-hero": {
                        "headline": "初始中文标题",
                        "subheadline": "初始中文副标题",
                    }
                }
            },
        }
        self.config_path.write_text(json.dumps(self.config_data, indent=2))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_apply_critique_from_directives_file(self):
        directives_dir = self.root / ".creative"
        directives_dir.mkdir(parents=True, exist_ok=True)
        directives_path = directives_dir / "review-directives.json"

        directives_content = {
            "directives": {
                "01-hero": {
                    "target": "mac_16_10",
                    "locale": "en-US",
                    "card_id": "01-hero",
                    "directive": "Tilt hero by 4 deg",
                    "patch": {
                        "headline": "Tilted Hero Headline",
                        "deviceOffset": {
                            "rotateX": 4.0,
                            "rotateY": 2.0,
                            "rotate": 0.0,
                            "scale": 1.05,
                            "x": 10.0,
                            "y": 20.0,
                        },
                    },
                }
            }
        }
        directives_path.write_text(json.dumps(directives_content, indent=2))

        result = apply_critique.apply_critique(repo_root=self.root)
        self.assertEqual(result["status"], "ok")
        self.assertIn("01-hero", result["updated_cards"])

        updated_config = json.loads(self.config_path.read_text())
        hero_card = updated_config["cards"][0]
        # Root headline is preserved; variant receives target-scoped override
        self.assertEqual(hero_card["headline"], "Original Headline")
        self.assertIn("mac_16_10", hero_card["variants"])
        mac_variant = hero_card["variants"]["mac_16_10"]
        self.assertEqual(mac_variant["headline"], "Tilted Hero Headline")
        self.assertEqual(mac_variant["deviceOffset"]["rotateX"], 4.0)
        self.assertEqual(mac_variant["deviceOffset"]["rotateY"], 2.0)
        self.assertEqual(mac_variant["deviceOffset"]["scale"], 1.05)
        self.assertEqual(mac_variant["deviceOffset"]["x"], 10.0)
        self.assertEqual(mac_variant["deviceOffset"]["y"], 20.0)

    def test_apply_critique_from_json_string(self):
        directives_json = json.dumps({
            "card_id": "02-features",
            "locale": "en-US",
            "patch": {
                "headline": "Updated Features Title",
                "deviceOffset": {"rotateX": 6.0, "scale": 1.02},
            },
        })

        result = apply_critique.apply_critique(
            repo_root=self.root,
            directives_json=directives_json,
        )
        self.assertEqual(result["status"], "ok")
        self.assertIn("02-features", result["updated_cards"])

        updated_config = json.loads(self.config_path.read_text())
        features_card = updated_config["cards"][1]
        self.assertEqual(features_card["headline"], "Updated Features Title")
        self.assertEqual(features_card["deviceOffset"]["rotateX"], 6.0)
        self.assertEqual(features_card["deviceOffset"]["scale"], 1.02)

    def test_apply_critique_localized_headline(self):
        directives_json = json.dumps({
            "card_id": "01-hero",
            "locale": "zh-Hans",
            "patch": {
                "headline": "优化后的中文标题",
            },
        })

        result = apply_critique.apply_critique(
            repo_root=self.root,
            directives_json=directives_json,
        )
        self.assertEqual(result["status"], "ok")

        updated_config = json.loads(self.config_path.read_text())
        # en-US root headline remains unchanged
        self.assertEqual(updated_config["cards"][0]["headline"], "Original Headline")
        # zh-Hans localized headline is updated
        self.assertEqual(
            updated_config["localizations"]["zh-Hans"]["01-hero"]["headline"],
            "优化后的中文标题",
        )

    def test_apply_critique_invalid_card_id(self):
        directives_json = json.dumps({
            "card_id": "nonexistent-card",
            "patch": {"headline": "Nope"},
        })
        with self.assertRaises(ValueError) as ctx:
            apply_critique.apply_critique(
                repo_root=self.root,
                directives_json=directives_json,
            )
        self.assertIn("nonexistent-card", str(ctx.exception))

    def test_cli_apply_critique_subcommand(self):
        directives_json = json.dumps({
            "card_id": "01-hero",
            "patch": {"headline": "CLI Ingested Headline"},
        })
        exit_code = cli.main([
            "apply-critique",
            "--repo", str(self.root),
            "--config", str(self.config_path),
            "--json", directives_json,
        ])
        self.assertEqual(exit_code, 0)

        updated_config = json.loads(self.config_path.read_text())
        self.assertEqual(updated_config["cards"][0]["headline"], "CLI Ingested Headline")

    def test_apply_critique_variant_localized_override(self):
        # Configure a card that has target-specific variant localizations
        variant_config = dict(self.config_data)
        variant_config["cards"][0]["variants"] = {
            "mac_16_10": {
                "localizations": {
                    "zh-Hans": {
                        "headline": "Mac专属初始中文标题"
                    }
                }
            }
        }
        cfg_path = self.root / "variant.config.json"
        cfg_path.write_text(json.dumps(variant_config, indent=2))

        directives_json = json.dumps({
            "target": "mac_16_10",
            "locale": "zh-Hans",
            "card_id": "01-hero",
            "patch": {
                "headline": "Mac专属优化中文标题"
            }
        })

        result = apply_critique.apply_critique(
            repo_root=self.root,
            config_path=cfg_path,
            directives_json=directives_json,
        )
        self.assertEqual(result["status"], "ok")

        updated = json.loads(cfg_path.read_text())
        # Variant-specific localization must be updated to prevent shadowing
        self.assertEqual(
            updated["cards"][0]["variants"]["mac_16_10"]["localizations"]["zh-Hans"]["headline"],
            "Mac专属优化中文标题",
        )

    def test_apply_critique_stdin(self):
        import io
        from unittest.mock import patch

        payload = json.dumps({
            "card_id": "01-hero",
            "patch": {"headline": "Stdin Headline"}
        })

        with patch("sys.stdin", io.StringIO(payload)):
            result = apply_critique.apply_critique(
                repo_root=self.root,
                directives_json="-",
            )
            self.assertEqual(result["status"], "ok")
            updated = json.loads(self.config_path.read_text())
    def test_apply_critique_skips_flat_items_without_patch(self):
        # A flat directive without explicit patch should be skipped, preventing inadvertent overwrite
        payload = json.dumps({
            "card_id": "01-hero",
            "headline": "Overwritten Headline",
            "notes": "Just some review notes",
        })
        result = apply_critique.apply_critique(
            repo_root=self.root,
            directives_json=payload,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["directives_applied"], 0)
        updated = json.loads(self.config_path.read_text())
        self.assertEqual(updated["cards"][0]["headline"], "Original Headline")

    def test_apply_critique_concurrent_mutation_rejected(self):
        # If the file on disk changes concurrently between read and write, raise ValueError
        payload = json.dumps({
            "card_id": "01-hero",
            "patch": {"headline": "Race Condition"}
        })
        # Simulate race condition by modifying file right after read
        orig_check = apply_critique.studio_contract.check_config

        def mutate_config_before_persist(cfg):
            orig_check(cfg)
            self.config_path.write_text(json.dumps({"mutated": True}))

        with unittest.mock.patch("apply_critique.studio_contract.check_config", side_effect=mutate_config_before_persist):
            with self.assertRaises(ValueError) as ctx:
                apply_critique.apply_critique(
                    repo_root=self.root,
                    directives_json=payload,
                )
            self.assertIn("concurrently", str(ctx.exception))

    def test_apply_critique_target_offset_preserves_card_baseline(self):
        # Card has baseline deviceOffset with x=40, y=20
        # Target directive supplies only rotateX=5.0
        # The variant must only contain rotateX=5.0 and not default x/y to 0
        payload = json.dumps({
            "card_id": "01-hero",
            "target": "mac_16_10",
            "patch": {
                "deviceOffset": {
                    "rotateX": 5.0
                }
            }
        })
        result = apply_critique.apply_critique(
            repo_root=self.root,
            directives_json=payload,
        )
        self.assertEqual(result["status"], "ok")
        updated = json.loads(self.config_path.read_text())
        variant_offset = updated["cards"][0]["variants"]["mac_16_10"]["deviceOffset"]
        self.assertEqual(variant_offset, {"rotateX": 5.0})
        self.assertNotIn("x", variant_offset)
        self.assertNotIn("y", variant_offset)

    def test_apply_critique_card_offset_preserves_omitted_fields(self):
        # Card 01-hero has deviceOffset in setUp: rotateX=0, rotateY=0, scale=1.0, x=0, y=0
        # First set x=40, y=20 on the card
        updated_cfg = json.loads(self.config_path.read_text())
        updated_cfg["cards"][0]["deviceOffset"] = {"x": 40.0, "y": 20.0, "scale": 1.05}
        self.config_path.write_text(json.dumps(updated_cfg, indent=2))

        # Directive updates only rotateX without target
        payload = json.dumps({
            "card_id": "01-hero",
            "patch": {
                "deviceOffset": {
                    "rotateX": 8.0
                }
            }
        })
        result = apply_critique.apply_critique(
            repo_root=self.root,
            directives_json=payload,
        )
        self.assertEqual(result["status"], "ok")
        saved = json.loads(self.config_path.read_text())
        offset = saved["cards"][0]["deviceOffset"]
        self.assertEqual(offset["rotateX"], 8.0)
        self.assertEqual(offset["x"], 40.0)
        self.assertEqual(offset["y"], 20.0)
        self.assertEqual(offset["scale"], 1.05)


if __name__ == "__main__":
    unittest.main()

