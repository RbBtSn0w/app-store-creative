import copy
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure runtime scripts can be imported
scripts_dir = Path(__file__).resolve().parent.parent / "plugins" / "app-store-creative" / "skills" / "app-store-creative" / "runtime" / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import app_store_creative
import ppo_experiment


SAMPLE_CONFIG = {
    "project": {
        "id": "sample-app",
        "name": "Sample App",
        "bundleId": "com.example.sample",
        "appStoreId": "1234567890",
    },
    "publishing": {
        "platform": "MAC_OS",
        "version": "1.0",
    },
    "storage": {
        "workspaceRoot": ".creative",
        "objectRoot": ".creative/objects",
        "releaseRoot": "releases",
    },
    "theme": {
        "headlineColor": "#FFFFFF",
        "subheadlineColor": "rgba(255, 255, 255, 0.8)",
        "fontFamily": "SF Pro Display",
        "background": {
            "type": "gradient",
            "colors": ["#070A14", "#16133B"],
            "angle": 145,
        },
    },
    "cards": [
        {
            "id": "01-hero",
            "headline": "Base Hero",
            "subheadline": "Base Subheadline",
            "deviceOffset": {"x": 10, "y": 20, "scale": 1.0, "rotateX": 2, "rotateY": 0},
        },
        {
            "id": "02-feature",
            "headline": "Base Feature",
            "subheadline": "Base Feature Sub",
            "deviceOffset": {"x": 0, "y": 0, "scale": 1.0},
        },
    ],
    "localizations": {
        "zh-Hans": {
            "01-hero": {
                "headline": "基础标题",
                "subheadline": "基础副标题",
            }
        }
    },
    "experiments": {
        "visual_style_cro": {
            "name": "3D Visual Style CRO Experiment",
            "trafficProportion": 50,
            "hypothesis": "Titanium cold gray drives higher enterprise conversion than Aurora purple.",
            "platform": "MAC_OS",
            "treatments": {
                "quartz_titanium": {
                    "name": "Treatment-Quartz-Titanium",
                    "theme": {
                        "background": {
                            "colors": ["#0B0E14", "#1B202B", "#2F3747"],
                            "angle": 160,
                        }
                    },
                    "cardOverrides": {
                        "01-hero": {
                            "deviceOffset": {"rotateX": 6},
                            "headline": "Titanium Hero",
                        }
                    },
                    "localizations": {
                        "zh-Hans": {
                            "01-hero": {
                                "headline": "钛金版标题"
                            }
                        }
                    },
                }
            },
        }
    },
}


class TestPPOExperiment(unittest.TestCase):
    def test_parse_experiments_empty(self):
        parsed = ppo_experiment.parse_experiments({})
        self.assertEqual(parsed, {})

    def test_parse_experiments_valid(self):
        parsed = ppo_experiment.parse_experiments(SAMPLE_CONFIG)
        self.assertIn("visual_style_cro", parsed)
        exp = parsed["visual_style_cro"]
        self.assertEqual(exp.name, "3D Visual Style CRO Experiment")
        self.assertEqual(exp.traffic_proportion, 50)
        self.assertEqual(exp.platform, "MAC_OS")
        self.assertIn("quartz_titanium", exp.treatments)
        treatment = exp.treatments["quartz_titanium"]
        self.assertEqual(treatment.name, "Treatment-Quartz-Titanium")
        self.assertEqual(treatment.theme["background"]["angle"], 160)

    def test_derive_treatment_config(self):
        derived = ppo_experiment.derive_treatment_config(SAMPLE_CONFIG, "visual_style_cro", "quartz_titanium")

        # 1. Theme override verification
        self.assertEqual(derived["theme"]["background"]["colors"], ["#0B0E14", "#1B202B", "#2F3747"])
        self.assertEqual(derived["theme"]["background"]["angle"], 160)
        self.assertEqual(derived["theme"]["headlineColor"], "#FFFFFF")  # Preserved

        # 2. Card override verification
        card01 = next(c for c in derived["cards"] if c["id"] == "01-hero")
        self.assertEqual(card01["headline"], "Titanium Hero")
        # Partial deviceOffset patch preserves baseline keys (x: 10, y: 20, scale: 1.0)
        self.assertEqual(card01["deviceOffset"]["rotateX"], 6)
        self.assertEqual(card01["deviceOffset"]["x"], 10)
        self.assertEqual(card01["deviceOffset"]["y"], 20)
        self.assertEqual(card01["deviceOffset"]["scale"], 1.0)

        # 3. Localized override verification
        zh_hero = derived["localizations"]["zh-Hans"]["01-hero"]
        self.assertEqual(zh_hero["headline"], "钛金版标题")
        self.assertEqual(zh_hero["subheadline"], "基础副标题")  # Preserved

        # 4. Storage workspace isolation
        self.assertEqual(derived["storage"]["workspaceRoot"], ".creative-quartz_titanium")
        self.assertEqual(derived["storage"]["objectRoot"], ".creative/objects-quartz_titanium")

        # 5. Metadata verification
        self.assertEqual(derived["_experiment"]["treatment_id"], "quartz_titanium")

    def test_derive_treatment_config_missing_keys(self):
        with self.assertRaisesRegex(KeyError, "not found"):
            ppo_experiment.derive_treatment_config(SAMPLE_CONFIG, "non_existent_exp", "treat")

        with self.assertRaisesRegex(KeyError, "not found"):
            ppo_experiment.derive_treatment_config(SAMPLE_CONFIG, "visual_style_cro", "non_existent_treat")

    def test_validate_platform_readiness_macos(self):
        # macOS with inflight edit draft is restricted
        r1 = ppo_experiment.validate_platform_readiness("MAC_OS", app_store_state="READY_FOR_SALE", has_inflight_version=True)
        self.assertFalse(r1["eligible"])
        self.assertEqual(r1["endpoint"], "v2")
        self.assertTrue(any("PREPARE_FOR_SUBMISSION" in reason for reason in r1["reasons"]))

        # macOS with non-live state is restricted
        r2 = ppo_experiment.validate_platform_readiness("MAC_OS", app_store_state="PREPARE_FOR_SUBMISSION", has_inflight_version=False)
        self.assertFalse(r2["eligible"])

        # macOS live store app with no inflight draft is eligible
        r3 = ppo_experiment.validate_platform_readiness("MAC_OS", app_store_state="READY_FOR_SALE", has_inflight_version=False)
        self.assertTrue(r3["eligible"])
        self.assertEqual(r3["endpoint"], "v2")

    def test_validate_platform_readiness_ios(self):
        r = ppo_experiment.validate_platform_readiness("IOS")
        self.assertTrue(r["eligible"])
        self.assertTrue(r["v1_supported"])
        self.assertTrue(r["v2_supported"])

    def test_compile_ppo_handoff(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            rel_root = repo_root / "releases" / "sample-app" / "MAC_OS" / "1.0"
            base_del = rel_root / "base_delivery_123"
            base_del.mkdir(parents=True)
            treat_del = rel_root / "treat_delivery_456"
            (treat_del / "media" / "en-US").mkdir(parents=True)
            (treat_del / "media" / "zh-Hans").mkdir(parents=True)

            out_file = repo_root / "ppo-handoff.json"
            handoff = ppo_experiment.compile_ppo_handoff(
                repo_root=repo_root,
                base_config=SAMPLE_CONFIG,
                experiment_id="visual_style_cro",
                baseline_delivery_id="base_delivery_123",
                treatment_deliveries={"quartz_titanium": "treat_delivery_456"},
                output_path=out_file,
            )

            self.assertEqual(handoff["schema_version"], 1)
            self.assertEqual(handoff["experiment"]["id"], "visual_style_cro")
            self.assertTrue(handoff["control"]["delivery_exists"])
            self.assertEqual(len(handoff["treatments"]), 1)
            t = handoff["treatments"][0]
            self.assertTrue(t["delivery_exists"])
            self.assertEqual(t["locales"], ["en-US", "zh-Hans"])
            self.assertTrue(out_file.is_file())

            # Check ASC command sequence
            asc_plan = handoff["asc_execution_plan"]
            self.assertTrue(any("asc product-pages experiments create --v2" in cmd for cmd in asc_plan))
            self.assertTrue(any("asc product-pages experiments treatments create" in cmd for cmd in asc_plan))
            self.assertTrue(any("asc product-pages experiments treatments localizations create" in cmd for cmd in asc_plan))

    def test_cli_ppo_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg_file = tmp_path / "creative.config.json"
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(SAMPLE_CONFIG, f)

            # 1. ppo list
            res_list = app_store_creative.run(
                app_store_creative.build_parser().parse_args(["ppo", "--repo", str(tmp_path), "list", "--config", str(cfg_file)])
            )
            self.assertIn("experiments", res_list)
            self.assertEqual(len(res_list["experiments"]), 1)
            self.assertEqual(res_list["experiments"][0]["id"], "visual_style_cro")

            # 2. ppo plan
            res_plan = app_store_creative.run(
                app_store_creative.build_parser().parse_args(["ppo", "--repo", str(tmp_path), "plan", "--config", str(cfg_file), "--experiment", "visual_style_cro"])
            )
            self.assertEqual(res_plan["experiment"]["id"], "visual_style_cro")
            self.assertIn("quartz_titanium", res_plan["treatments"])

    def test_reproduce_defaults_platform_and_locale_groups(self):
        cfg = copy.deepcopy(SAMPLE_CONFIG)
        cfg.pop("storage")
        cfg["project"]["locales"] = ["en-US", "fr-FR"]
        cfg["targets"] = ["iphone_6_9"]
        cfg["experiments"]["visual_style_cro"]["platform"] = "IOS"
        derived = ppo_experiment.derive_treatment_config(cfg, "visual_style_cro", "quartz_titanium")
        self.assertEqual(derived["storage"]["workspaceRoot"], ".creative-quartz_titanium")
        self.assertEqual(derived["publishing"]["platform"], "IOS")
        plan = ppo_experiment.ppo_reproduce_plan(cfg, "visual_style_cro", "quartz_titanium")
        self.assertEqual([g["locale"] for g in plan["scope"]["by_locale"]], ["en-US", "fr-FR"])
        self.assertEqual(plan["scope"]["by_locale"][0]["targets"], ["iphone_6_9"])

    def test_treatment_identifier_cannot_escape_storage_namespace(self):
        cfg = copy.deepcopy(SAMPLE_CONFIG)
        treatments = cfg["experiments"]["visual_style_cro"]["treatments"]
        treatments["../escape"] = treatments.pop("quartz_titanium")
        derived = ppo_experiment.derive_treatment_config(cfg, "visual_style_cro", "../escape")
        self.assertNotIn("..", derived["storage"]["workspaceRoot"])
        self.assertEqual(Path(derived["storage"]["workspaceRoot"]).parent, Path("."))

    def test_execute_keeps_owned_config_and_preserves_existing_file(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "creative.config.json"
            cfg.write_text(json.dumps(SAMPLE_CONFIG))
            existing = root / "ppo-reproduce-quartz_titanium.json"
            existing.write_text("original")
            paths = []
            def produce(repo, config_path, **kwargs):
                paths.append(config_path)
                return {"status": "PASS"}
            args = app_store_creative.build_parser().parse_args([
                "ppo", "--repo", str(root), "reproduce", "--experiment", "visual_style_cro",
                "--variant", "quartz_titanium", "--execute"])
            with patch("production_lifecycle.produce", side_effect=produce):
                result = app_store_creative.run(args)
            self.assertEqual(existing.read_text(), "original")
            self.assertTrue(paths[0].is_file())
            self.assertEqual(Path(result["config_path"]), paths[0])

    def test_ppo_reproduce_dry_run_plan(self):
        # PRD-006 R2: dry-run output contains provenance header, locale-grouped
        # plan, and summary counts without storage mutation.
        import app_store_creative
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg_file = tmp_path / "creative.config.json"
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(SAMPLE_CONFIG, f)
            res = app_store_creative.run(
                app_store_creative.build_parser().parse_args([
                    "ppo", "--repo", str(tmp_path), "reproduce",
                    "--config", str(cfg_file),
                    "--experiment", "visual_style_cro",
                    "--variant", "quartz_titanium",
                    "--decision-basis", "test decision",
                ])
            )
        self.assertEqual(res["provenance"]["experiment_id"], "visual_style_cro")
        self.assertEqual(res["provenance"]["variant_id"], "quartz_titanium")
        self.assertEqual(res["provenance"]["decision_basis"], "test decision")
        self.assertTrue(res["dry_run"])
        self.assertIn("planned_delivery_count", res["scope"])
        # Per-treatment namespace (R1b) matches derive_treatment_config layout.
        self.assertEqual(res["treatment_config"]["storage_workspace"], ".creative-quartz_titanium")
        self.assertEqual(res["treatment_config"]["experiment_stamp"]["treatment_id"], "quartz_titanium")

    def test_ppo_reproduce_rejects_unknown_variant(self):
        import app_store_creative
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg_file = tmp_path / "creative.config.json"
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(SAMPLE_CONFIG, f)
            with self.assertRaisesRegex(KeyError, "not found"):
                app_store_creative.run(
                    app_store_creative.build_parser().parse_args([
                        "ppo", "--repo", str(tmp_path), "reproduce",
                        "--config", str(cfg_file),
                        "--experiment", "visual_style_cro",
                        "--variant", "does_not_exist",
                    ])
                )

            # 3. ppo handoff
            out_json = tmp_path / "out-handoff.json"
            res_handoff = app_store_creative.run(
                app_store_creative.build_parser().parse_args([
                    "ppo",
                    "--repo", str(tmp_path),
                    "handoff",
                    "--config", str(cfg_file),
                    "--experiment", "visual_style_cro",
                    "--baseline-delivery", "del_base_1",
                    "--treatment-delivery", "quartz_titanium:del_treat_1",
                    "--output", str(out_json),
                ])
            )
            self.assertEqual(res_handoff["control"]["delivery_id"], "del_base_1")
            self.assertTrue(out_json.is_file())

    def test_platform_readiness_tv_and_vision_os(self):
        r_tv = ppo_experiment.validate_platform_readiness("TV_OS")
        self.assertEqual(r_tv["platform"], "TV_OS")
        self.assertTrue(r_tv["eligible"])
        self.assertEqual(r_tv["endpoint"], "v2")
        self.assertFalse(r_tv["v1_supported"])
        self.assertTrue(r_tv["v2_supported"])

        r_vis = ppo_experiment.validate_platform_readiness("VISION_OS")
        self.assertEqual(r_vis["platform"], "VISION_OS")
        self.assertTrue(r_vis["eligible"])
        self.assertEqual(r_vis["endpoint"], "v2")

    def test_compile_ppo_handoff_shell_quoting(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            special_config = copy.deepcopy(SAMPLE_CONFIG)
            special_config["experiments"]["visual_style_cro"]["name"] = 'Holiday "Sale" & $Special'
            special_config["experiments"]["visual_style_cro"]["treatments"]["quartz_titanium"]["name"] = "Variant 'A' & B"
            special_config["experiments"]["visual_style_cro"]["treatments"]["quartz_titanium"]["appIconName"] = "Icon $1"

            handoff = ppo_experiment.compile_ppo_handoff(
                repo_root=tmp_path,
                base_config=special_config,
                experiment_id="visual_style_cro",
                baseline_delivery_id="del_base",
                treatment_deliveries={"quartz_titanium": "del_treat"},
                output_path=tmp_path / "handoff.json",
            )

            plan = handoff["asc_execution_plan"]
            expected_exp = shlex.quote('Holiday "Sale" & $Special')
            expected_treat = shlex.quote("Variant 'A' & B")
            expected_icon = shlex.quote("Icon $1")
            self.assertTrue(any(f"--name {expected_exp}" in cmd for cmd in plan))
            self.assertTrue(any(f"--name {expected_treat}" in cmd for cmd in plan))
            self.assertTrue(any(f"--app-icon-name {expected_icon}" in cmd for cmd in plan))

    def test_parse_experiments_validation(self):
        # Not a dict
        with self.assertRaisesRegex(ValueError, "'experiments' must be an object/dict"):
            ppo_experiment.parse_experiments({"experiments": "invalid"})

        # Missing name
        with self.assertRaisesRegex(ValueError, "requires a non-empty string 'name'"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"trafficProportion": 50, "treatments": {"t1": {"name": "T1"}}}}})

        # Invalid trafficProportion
        with self.assertRaisesRegex(ValueError, "trafficProportion must be an integer between 1 and 100"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"name": "E1", "trafficProportion": 150, "treatments": {"t1": {"name": "T1"}}}}})

        # Invalid platform
        with self.assertRaisesRegex(ValueError, "invalid platform 'ANDROID'"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"name": "E1", "trafficProportion": 50, "platform": "ANDROID", "treatments": {"t1": {"name": "T1"}}}}})

        # Empty treatments
        with self.assertRaisesRegex(ValueError, "must define at least one treatment"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"name": "E1", "trafficProportion": 50, "treatments": {}}}})

        # Treatment missing name
        with self.assertRaisesRegex(ValueError, "requires a non-empty string 'name'"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"name": "E1", "trafficProportion": 50, "treatments": {"t1": {}}}}})

    def test_macos_readiness_without_state(self):
        r = ppo_experiment.validate_platform_readiness("MAC_OS")
        self.assertFalse(r["eligible"])
        self.assertTrue(any("Store state has not been verified" in reason for reason in r["reasons"]))

    def test_cli_treatment_delivery_validation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg_file = tmp_path / "creative.config.json"
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(SAMPLE_CONFIG, f)

            parser = app_store_creative.build_parser()

            # Malformed entry without colon
            with self.assertRaisesRegex(ValueError, "Malformed --treatment-delivery"):
                app_store_creative.run(
                    parser.parse_args([
                        "ppo", "--repo", str(tmp_path), "handoff",
                        "--config", str(cfg_file),
                        "--experiment", "visual_style_cro",
                        "--treatment-delivery", "malformed_entry",
                    ])
                )

            # Unknown treatment ID
            with self.assertRaisesRegex(ValueError, "Unknown treatment ID 'nonexistent'"):
                app_store_creative.run(
                    parser.parse_args([
                        "ppo", "--repo", str(tmp_path), "handoff",
                        "--config", str(cfg_file),
                        "--experiment", "visual_style_cro",
                        "--treatment-delivery", "nonexistent:del123",
                    ])
                )

    def test_traffic_proportion_rejects_non_integers_and_bool(self):
        # Reject float
        with self.assertRaisesRegex(ValueError, "trafficProportion must be an integer between 1 and 100"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"name": "E1", "trafficProportion": 12.9, "treatments": {"t1": {"name": "T1"}}}}})

        # Reject bool
        with self.assertRaisesRegex(ValueError, "trafficProportion must be an integer between 1 and 100"):
            ppo_experiment.parse_experiments({"experiments": {"exp1": {"name": "E1", "trafficProportion": True, "treatments": {"t1": {"name": "T1"}}}}})

    def test_platform_normalization(self):
        parsed = ppo_experiment.parse_experiments({
            "experiments": {
                "exp1": {
                    "name": "E1",
                    "trafficProportion": 50,
                    "platform": "mac_os",
                    "treatments": {"t1": {"name": "T1"}},
                }
            }
        })
        self.assertEqual(parsed["exp1"].platform, "MAC_OS")

    def test_v2_command_generation_for_tv_and_vision_os(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg = copy.deepcopy(SAMPLE_CONFIG)
            cfg["experiments"]["visual_style_cro"]["platform"] = "TV_OS"
            handoff_tv = ppo_experiment.compile_ppo_handoff(
                repo_root=tmp_path,
                base_config=cfg,
                experiment_id="visual_style_cro",
                baseline_delivery_id="del_base",
                treatment_deliveries={"quartz_titanium": "del_treat"},
            )
            self.assertTrue(any("--v2 --app 1234567890 --platform TV_OS" in cmd for cmd in handoff_tv["asc_execution_plan"]))

            cfg["experiments"]["visual_style_cro"]["platform"] = "VISION_OS"
            handoff_vision = ppo_experiment.compile_ppo_handoff(
                repo_root=tmp_path,
                base_config=cfg,
                experiment_id="visual_style_cro",
                baseline_delivery_id="del_base",
                treatment_deliveries={"quartz_titanium": "del_treat"},
            )
            self.assertTrue(any("--v2 --app 1234567890 --platform VISION_OS" in cmd for cmd in handoff_vision["asc_execution_plan"]))

    def test_cli_repo_preservation_pre_and_post_action(self):
        parser = app_store_creative.build_parser()

        # Pre-action --repo
        args1 = parser.parse_args(["ppo", "--repo", "/custom/repo", "list"])
        self.assertEqual(str(args1.repo), "/custom/repo")

        # Post-action --repo
        args2 = parser.parse_args(["ppo", "list", "--repo", "/custom/repo2"])
        self.assertEqual(str(args2.repo), "/custom/repo2")

    def test_compile_ppo_handoff_default_storage_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg = copy.deepcopy(SAMPLE_CONFIG)
            # Remove explicit storage configuration to test default fallback to STORAGE_DEFAULTS['releaseRoot']
            cfg.pop("storage", None)

            # Create default release structure under creative-releases
            base_del = tmp_path / "creative-releases" / "sample-app" / "MAC_OS" / "1.0" / "del_base"
            base_del.mkdir(parents=True)
            treat_del = tmp_path / "creative-releases" / "sample-app" / "MAC_OS" / "1.0" / "del_treat"
            treat_media = treat_del / "media" / "en-US"
            treat_media.mkdir(parents=True)

            handoff = ppo_experiment.compile_ppo_handoff(
                repo_root=tmp_path,
                base_config=cfg,
                experiment_id="visual_style_cro",
                baseline_delivery_id="del_base",
                treatment_deliveries={"quartz_titanium": "del_treat"},
            )

            self.assertTrue(handoff["control"]["delivery_exists"])
            self.assertEqual(handoff["treatments"][0]["delivery_id"], "del_treat")
            self.assertTrue(handoff["treatments"][0]["delivery_exists"])
            self.assertIn("en-US", handoff["treatments"][0]["locales"])

    def test_compile_ppo_handoff_invalid_storage_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg = copy.deepcopy(SAMPLE_CONFIG)
            cfg["storage"]["releaseRoot"] = "../outside"
            with self.assertRaises(ValueError):
                ppo_experiment.compile_ppo_handoff(
                    repo_root=tmp_path,
                    base_config=cfg,
                    experiment_id="visual_style_cro",
                    baseline_delivery_id="del_base",
                    treatment_deliveries={"quartz_titanium": "del_treat"},
                )


if __name__ == "__main__":
    unittest.main()
