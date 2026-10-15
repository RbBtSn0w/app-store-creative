#!/usr/bin/env python3
"""Stable command-line interface for the local App Store creative workflow (v2.0)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit("App Store Creative requires Python 3.11 or newer")

# Ensure script directory is in sys.path for direct script imports
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

import apply_critique
import companion_generator
import lifecycle_commands
import ppo_experiment
import production_lifecycle
import studio_server


def run(args):
    root = (args.repo or Path.cwd()).resolve()
    def project_path(value):
        return (value if value.is_absolute() else root / value).resolve() if value else None

    if args.command in ("history", "preview", "run", "attempt", "artifact", "candidate", "inventory", "storage", "approval", "delivery", "archive", "publication", "cleanup", "incident", "input"):
        return lifecycle_commands.execute(args)

    # Modern v2 commands
    if args.command in ("dev", "studio"):
        cfg = project_path(getattr(args, "config", None))
        studio_server.run_studio_server(port=args.port, repo_root=root, config_path=cfg)
        return {"status": "ok", "message": f"Studio stopped on port {args.port}"}

    if args.command == "companion":
        cfg = project_path(getattr(args, "config", None))
        out = project_path(getattr(args, "output", None))
        return companion_generator.generate_companion(
            repo_root=root,
            config_path=cfg,
            output_path=out,
            target=getattr(args, "target", None),
            locale=getattr(args, "locale", None),
        )

    if args.command == "apply-critique":
        cfg = project_path(getattr(args, "config", None))
        d_file = project_path(getattr(args, "file", None))
        d_json = getattr(args, "json", None)
        return apply_critique.apply_critique(
            repo_root=root,
            config_path=cfg,
            directives_file=d_file,
            directives_json=d_json,
        )

    if args.command == "export":
        if getattr(args, 'output_dir', None):
            raise ValueError('export --output-dir is unsupported for managed attempts; configure storage.workspaceRoot in creative.config.json instead (and storage.objectRoot for retained media)')
        cfg = project_path(getattr(args, 'config', None))
        return production_lifecycle.produce(root, cfg, targets=getattr(args, 'targets', None),
            locales=getattr(args, 'locales', None), with_video=getattr(args, 'with_video', False))

    if args.command == "ppo":
        cfg = project_path(getattr(args, "config", None))
        if cfg is None:
            cfg = root / "creative.config.json"
        if not cfg.is_file():
            raise FileNotFoundError(f"Configuration file not found: {cfg}")
        with open(cfg, "r", encoding="utf-8") as f:
            base_config = json.load(f)

        if args.ppo_action == "list":
            experiments = ppo_experiment.parse_experiments(base_config)
            return {
                "experiments": [
                    {
                        "id": exp.id,
                        "name": exp.name,
                        "traffic_proportion": exp.traffic_proportion,
                        "hypothesis": exp.hypothesis,
                        "platform": exp.platform,
                        "treatments": [
                            {"id": t.id, "name": t.name, "app_icon_name": t.app_icon_name}
                            for t in exp.treatments.values()
                        ],
                    }
                    for exp in experiments.values()
                ]
            }

        if args.ppo_action == "plan":
            exp_id = args.experiment
            experiments = ppo_experiment.parse_experiments(base_config)
            if exp_id not in experiments:
                raise KeyError(f"Experiment '{exp_id}' not found in configuration")
            exp = experiments[exp_id]
            treatment_plans = {}
            for t_id in exp.treatments:
                derived = ppo_experiment.derive_treatment_config(base_config, exp_id, t_id)
                treatment_plans[t_id] = {
                    "name": exp.treatments[t_id].name,
                    "theme": derived.get("theme", {}),
                    "cards_count": len(derived.get("cards", [])),
                    "storage": derived.get("storage", {}),
                }
            return {
                "experiment": {
                    "id": exp.id,
                    "name": exp.name,
                    "traffic_proportion": exp.traffic_proportion,
                    "hypothesis": exp.hypothesis,
                    "platform": exp.platform,
                },
                "platform_readiness": ppo_experiment.validate_platform_readiness(exp.platform or "MAC_OS"),
                "treatments": treatment_plans,
            }

        if args.ppo_action == "handoff":
            exp_id = args.experiment
            experiments = ppo_experiment.parse_experiments(base_config)
            if exp_id not in experiments:
                raise KeyError(f"Experiment '{exp_id}' not found in configuration")
            exp = experiments[exp_id]
            baseline_del = getattr(args, "baseline_delivery", None)
            treatment_del_map = {}
            for item in (getattr(args, "treatment_deliveries", None) or []):
                if ":" not in item:
                    raise ValueError(f"Malformed --treatment-delivery value '{item}': expected format 'treatment_id:delivery_id'")
                tid, did = item.split(":", 1)
                tid, did = tid.strip(), did.strip()
                if tid not in exp.treatments:
                    raise ValueError(f"Unknown treatment ID '{tid}' in --treatment-delivery. Known treatments: {list(exp.treatments.keys())}")
                treatment_del_map[tid] = did
            out_path = project_path(getattr(args, "output", None))
            return ppo_experiment.compile_ppo_handoff(
                repo_root=root,
                base_config=base_config,
                experiment_id=exp_id,
                baseline_delivery_id=baseline_del or "<BASELINE_DELIVERY_ID>",
                treatment_deliveries=treatment_del_map,
                output_path=out_path,
            )

    raise AssertionError(args.command)


def build_parser():
    p = argparse.ArgumentParser(description="App Store Creative CLI (v2.0)")
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name):
        x = sub.add_parser(name)
        x.add_argument("--repo", type=Path, default=Path.cwd())
        return x

    lifecycle_commands.add_commands(sub)

    # Modern v2 Subcommands
    for name in ("dev", "studio"):
        dev = cmd(name)
        dev.add_argument("--config", type=Path, help="Path to creative.config.json")
        dev.add_argument("--port", type=int, default=3100, help="Local studio port (default 3100)")

    comp = cmd("companion")
    comp.add_argument("--config", type=Path, help="Path to creative.config.json")
    comp.add_argument("--output", type=Path, help="Output path for companion HTML (default .creative/companion.html)")
    comp.add_argument("--target", type=str, help="Specific target to preview (e.g. mac_16_10)")
    comp.add_argument("--locale", type=str, help="Specific locale to preview (e.g. en-US)")

    crit = cmd("apply-critique")
    crit.add_argument("--config", type=Path, help="Path to creative.config.json")
    crit.add_argument("--file", type=Path, help="Path to review-directives.json (default .creative/review-directives.json)")
    crit.add_argument("--json", type=str, help="Direct JSON string containing directives")

    exp = cmd("export")
    exp.add_argument("--config", type=Path, help="Path to creative.config.json")
    exp.add_argument("--output-dir", type=Path, help="Unsupported for managed export; configure storage.workspaceRoot in creative.config.json instead")
    exp.add_argument("--target", action="append", dest="targets", help="Specific target to export (repeatable)")
    exp.add_argument("--locale", action="append", dest="locales", help="Specific locale to export (repeatable)")
    exp.add_argument("--with-video", action="store_true", help="Also synthesize App Preview video")

    ppo = cmd("ppo")
    ppo_sub = ppo.add_subparsers(dest="ppo_action", required=True)

    ppo_list = ppo_sub.add_parser("list", help="List experiments defined in creative.config.json")
    ppo_list.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
    ppo_list.add_argument("--config", type=Path, help="Path to creative.config.json")

    ppo_plan = ppo_sub.add_parser("plan", help="Compile and inspect PPO experiment execution plan")
    ppo_plan.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
    ppo_plan.add_argument("--config", type=Path, help="Path to creative.config.json")
    ppo_plan.add_argument("--experiment", type=str, required=True, help="Experiment ID to plan")

    ppo_handoff = ppo_sub.add_parser("handoff", help="Compile ppo-handoff.json and ASC execution plan")
    ppo_handoff.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
    ppo_handoff.add_argument("--config", type=Path, help="Path to creative.config.json")
    ppo_handoff.add_argument("--experiment", type=str, required=True, help="Experiment ID")
    ppo_handoff.add_argument("--baseline-delivery", type=str, help="Delivery ID of baseline / control")
    ppo_handoff.add_argument("--treatment-delivery", action="append", dest="treatment_deliveries", help="Treatment delivery mapping (treatment_id:delivery_id)")
    ppo_handoff.add_argument("--output", type=Path, help="Output path for ppo-handoff.json")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        res = run(args)
        if res is not None:
            print(json.dumps(res, sort_keys=True, ensure_ascii=False, indent=2))
        # Ensure CI gates fail if validation reported FAIL
        if isinstance(res, dict) and res.get("status") == "FAIL":
            return 2
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
