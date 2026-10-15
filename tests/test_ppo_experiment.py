import json
import pytest
from pathlib import Path
import sys

# Ensure runtime scripts can be imported
scripts_dir = Path(__file__).resolve().parent.parent / "plugins" / "app-store-creative" / "skills" / "app-store-creative" / "runtime" / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import ppo_experiment
import app_store_creative


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


def test_parse_experiments_empty():
    parsed = ppo_experiment.parse_experiments({})
    assert parsed == {}


def test_parse_experiments_valid():
    parsed = ppo_experiment.parse_experiments(SAMPLE_CONFIG)
    assert "visual_style_cro" in parsed
    exp = parsed["visual_style_cro"]
    assert exp.name == "3D Visual Style CRO Experiment"
    assert exp.traffic_proportion == 50
    assert exp.platform == "MAC_OS"
    assert "quartz_titanium" in exp.treatments
    treatment = exp.treatments["quartz_titanium"]
    assert treatment.name == "Treatment-Quartz-Titanium"
    assert treatment.theme["background"]["angle"] == 160


def test_derive_treatment_config():
    derived = ppo_experiment.derive_treatment_config(SAMPLE_CONFIG, "visual_style_cro", "quartz_titanium")

    # 1. Theme override verification
    assert derived["theme"]["background"]["colors"] == ["#0B0E14", "#1B202B", "#2F3747"]
    assert derived["theme"]["background"]["angle"] == 160
    assert derived["theme"]["headlineColor"] == "#FFFFFF"  # Preserved

    # 2. Card override verification
    card01 = next(c for c in derived["cards"] if c["id"] == "01-hero")
    assert card01["headline"] == "Titanium Hero"
    # Partial deviceOffset patch preserves baseline keys (x: 10, y: 20, scale: 1.0)
    assert card01["deviceOffset"]["rotateX"] == 6
    assert card01["deviceOffset"]["x"] == 10
    assert card01["deviceOffset"]["y"] == 20
    assert card01["deviceOffset"]["scale"] == 1.0

    # 3. Localized override verification
    zh_hero = derived["localizations"]["zh-Hans"]["01-hero"]
    assert zh_hero["headline"] == "钛金版标题"
    assert zh_hero["subheadline"] == "基础副标题"  # Preserved

    # 4. Storage workspace isolation
    assert derived["storage"]["workspaceRoot"] == ".creative-quartz_titanium"
    assert derived["storage"]["objectRoot"] == ".creative/objects-quartz_titanium"

    # 5. Metadata verification
    assert derived["_experiment"]["treatment_id"] == "quartz_titanium"


def test_derive_treatment_config_missing_keys():
    with pytest.raises(KeyError, match="not found"):
        ppo_experiment.derive_treatment_config(SAMPLE_CONFIG, "non_existent_exp", "treat")

    with pytest.raises(KeyError, match="not found"):
        ppo_experiment.derive_treatment_config(SAMPLE_CONFIG, "visual_style_cro", "non_existent_treat")


def test_validate_platform_readiness_macos():
    # macOS with inflight edit draft is restricted
    r1 = ppo_experiment.validate_platform_readiness("MAC_OS", app_store_state="READY_FOR_SALE", has_inflight_version=True)
    assert r1["eligible"] is False
    assert r1["endpoint"] == "v2"
    assert any("PREPARE_FOR_SUBMISSION" in reason for reason in r1["reasons"])

    # macOS with non-live state is restricted
    r2 = ppo_experiment.validate_platform_readiness("MAC_OS", app_store_state="PREPARE_FOR_SUBMISSION", has_inflight_version=False)
    assert r2["eligible"] is False

    # macOS live store app with no inflight draft is eligible
    r3 = ppo_experiment.validate_platform_readiness("MAC_OS", app_store_state="READY_FOR_SALE", has_inflight_version=False)
    assert r3["eligible"] is True
    assert r3["endpoint"] == "v2"


def test_validate_platform_readiness_ios():
    r = ppo_experiment.validate_platform_readiness("IOS")
    assert r["eligible"] is True
    assert r["v1_supported"] is True
    assert r["v2_supported"] is True


def test_compile_ppo_handoff(tmp_path):
    repo_root = tmp_path
    rel_root = repo_root / "releases" / "sample-app" / "MAC_OS" / "1.0"
    base_del = rel_root / "base_delivery_123"
    base_del.mkdir(parents=True)
    treat_del = rel_root / "treat_delivery_456"
    (treat_del / "media" / "en-US").mkdir(parents=True)
    (treat_del / "media" / "zh-Hans").mkdir(parents=True)

    out_file = tmp_path / "ppo-handoff.json"
    handoff = ppo_experiment.compile_ppo_handoff(
        repo_root=repo_root,
        base_config=SAMPLE_CONFIG,
        experiment_id="visual_style_cro",
        baseline_delivery_id="base_delivery_123",
        treatment_deliveries={"quartz_titanium": "treat_delivery_456"},
        output_path=out_file,
    )

    assert handoff["schema_version"] == 1
    assert handoff["experiment"]["id"] == "visual_style_cro"
    assert handoff["control"]["delivery_exists"] is True
    assert len(handoff["treatments"]) == 1
    t = handoff["treatments"][0]
    assert t["delivery_exists"] is True
    assert t["locales"] == ["en-US", "zh-Hans"]
    assert out_file.is_file()

    # Check ASC command sequence
    asc_plan = handoff["asc_execution_plan"]
    assert any("asc product-pages experiments create --v2" in cmd for cmd in asc_plan)
    assert any("asc product-pages experiments treatments create" in cmd for cmd in asc_plan)
    assert any("asc product-pages experiments treatments localizations create" in cmd for cmd in asc_plan)


def test_cli_ppo_dispatch(tmp_path):
    cfg_file = tmp_path / "creative.config.json"
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_CONFIG, f)

    # 1. ppo list
    res_list = app_store_creative.run(
        app_store_creative.build_parser().parse_args(["ppo", "--repo", str(tmp_path), "list", "--config", str(cfg_file)])
    )
    assert "experiments" in res_list
    assert len(res_list["experiments"]) == 1
    assert res_list["experiments"][0]["id"] == "visual_style_cro"

    # 2. ppo plan
    res_plan = app_store_creative.run(
        app_store_creative.build_parser().parse_args(["ppo", "--repo", str(tmp_path), "plan", "--config", str(cfg_file), "--experiment", "visual_style_cro"])
    )
    assert res_plan["experiment"]["id"] == "visual_style_cro"
    assert "quartz_titanium" in res_plan["treatments"]

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
    assert res_handoff["control"]["delivery_id"] == "del_base_1"
    assert out_json.is_file()
