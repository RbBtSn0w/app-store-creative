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
import ppo_assessment
import ppo_experiment
import production_lifecycle
import studio_server


def run(args):
    root = (args.repo or Path.cwd()).resolve()
    def project_path(value):
        return (value if value.is_absolute() else root / value).resolve() if value else None

    if args.command in ("history", "preview", "run", "attempt", "artifact", "candidate", "inventory", "storage", "approval", "delivery", "archive", "publication", "cleanup", "incident", "input", "audit"):
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
            locales=getattr(args, 'locales', None), with_video=getattr(args, 'with_video', False),
            require_declared_video=True)

    if args.command == "ppo":
        cfg = project_path(getattr(args, "config", None))
        if cfg is None:
            cfg = root / "creative.config.json"
        if not cfg.is_file():
            raise FileNotFoundError(f"Configuration file not found: {cfg}")
        from configuration_layers import load
        base_config = load(root, cfg).config

        if args.ppo_action == "bind":
            mapping = {}
            for item in args.treatment_id:
                local, separator, remote = item.partition(':')
                if not separator or local in mapping:
                    raise ValueError('Expected a unique local:remote treatment ID mapping')
                mapping[local] = remote
            bound = ppo_assessment.bind(root, base_config, project_path(args.handoff),
                                        args.app_id, args.asc_experiment_id, mapping)
            return ppo_assessment.write_once(project_path(args.output), bound)

        if args.ppo_action == "assess":
            assessed = ppo_assessment.assess(root, base_config, project_path(args.handoff),
                                             project_path(args.binding), project_path(args.snapshot))
            if args.output:
                ppo_assessment.write_once(project_path(args.output), assessed)
            return assessed

        if args.ppo_action == "result":
            manual = [args.market, args.change, args.observation, args.evidence, args.decision]
            if args.assessment:
                if any(value is not None for value in [*manual, args.treatment]):
                    raise ValueError('--assessment cannot be combined with manual decision fields')
                result = ppo_assessment.assessed_result(root, base_config, project_path(args.handoff),
                                                        project_path(args.assessment))
                return ppo_assessment.write_once(project_path(args.output), result)
            if not all(manual):
                raise ValueError('Supply an assessment or all manual decision fields')
            return ppo_experiment.record_result(base_config, project_path(args.handoff), project_path(args.output),
                market=args.market, change=args.change, observation=args.observation, evidence=args.evidence,
                decision=args.decision, treatment=args.treatment)

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
                **({"preflight": ppo_assessment.preflight(base_config, base_config["experiments"][exp_id])}
                   if "policy" in base_config["experiments"][exp_id] else {}),
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
                if tid in treatment_del_map:
                    raise ValueError(f'Duplicate delivery mapping for {tid}')
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

        if args.ppo_action == "reproduce":
            exp_id = args.experiment
            experiments = ppo_experiment.parse_experiments(base_config)
            if exp_id not in experiments:
                raise KeyError(f"Experiment '{exp_id}' not found in configuration")
            variant = args.variant
            decision_basis = args.decision_basis or "explicit --variant selection"
            measured_scope = expected_assets = None
            if args.result:
                variant, decision_basis = ppo_experiment.selected_result(base_config, exp_id, project_path(args.result))
                result_record = ppo_assessment.read(project_path(args.result))
                if result_record.get('schema_version') == 2 or 'assessment_sha256' in result_record:
                    expected_assets = ppo_assessment.replay_selection(root, base_config, result_record)
                    measured_scope = result_record['measured_scope']
            plan = ppo_experiment.ppo_reproduce_plan(
                base_config=base_config,
                experiment_id=exp_id,
                variant_id=variant,
                decision_basis=decision_basis, measured_scope=measured_scope,
            )
            if measured_scope:
                plan['provenance']['assessment_sha256'] = result_record['assessment_sha256']
                plan['provenance']['selected_delivery'] = result_record['selected_delivery']
                plan['provenance']['measured_scope'] = measured_scope
                derived = ppo_experiment.derive_treatment_config(base_config, exp_id, variant)
                plan['screenshot_order'] = [card['id'] for card in derived['cards']]
                production_root, cfg_path = ppo_assessment.reproduction_project(
                    root, base_config, result_record, derived, args.execute)
                plan['treatment_config'].update(storage_workspace=str(production_root / '.creative'),
                                                storage_objects=str(production_root / '.creative/objects'))
            if args.execute:
                from production_lifecycle import produce as managed_produce
                if not measured_scope:
                    import tempfile
                    production_root = root
                    derived = ppo_experiment.derive_treatment_config(base_config, exp_id, variant)
                    with tempfile.NamedTemporaryFile(mode="w", prefix="ppo-reproduce-", suffix=".json",
                                                     dir=root, encoding="utf-8", delete=False) as config_file:
                        json.dump(derived, config_file, indent=2, ensure_ascii=False)
                        cfg_path = Path(config_file.name)
                production_options = dict(measured_scope, expected_screenshots=expected_assets) if measured_scope else {}
                result = managed_produce(production_root, cfg_path, experiment_provenance=plan['provenance'], **production_options)
                result["config_path"] = str(cfg_path)
                result["provenance"] = plan["provenance"]
                return result
            return plan

    if args.command == "bgm":
        import bgm_lifecycle
        return _run_bgm(args, bgm_lifecycle, project_path)

    raise AssertionError(args.command)


def _run_bgm(args, bgm_lifecycle, project_path):
    """Dispatch bgm subcommands (scan / recommend / compose)."""
    if args.bgm_action == "scan":
        catalog = bgm_lifecycle.scan_catalog(library_root=args.library)
        output = project_path(args.output)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
            return {"status": "ok", "catalog_path": str(output),
                    "total_files": catalog["total_files"], "music_loops": catalog["music_loops"],
                    "available": catalog["available"]}
        return catalog

    if args.bgm_action == "recommend":
        catalog = json.loads(project_path(args.catalog).read_text())
        if args.context:
            context = json.loads(project_path(args.context).read_text())
        elif args.context_json:
            context = json.loads(args.context_json)
        else:
            context = {}
        result = bgm_lifecycle.recommend(catalog, context, count=args.count)
        output = project_path(args.output)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            return {"status": "ok", "recommendations_path": str(output),
                    "available": result["available"], "candidates": len(result["candidates"])}
        return result

    if args.bgm_action == "compose":
        receipt = bgm_lifecycle.compose(
            loop_path=project_path(args.loop),
            video_path=project_path(args.video),
            output_path=project_path(args.output),
            fade_in=args.fade_in,
            fade_out_start=args.fade_out_start,
            fade_out_duration=args.fade_out_duration,
            target_lufs=args.target_lufs,
            true_peak_ceiling=args.true_peak_ceiling,
        )
        receipt_path = project_path(args.receipt)
        if receipt_path:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
        result = {"status": "ok", "output": receipt["output"],
                  "final_lufs": receipt["final_native_lufs"],
                  "final_peak_dbtp": receipt["final_native_guarded_peak_dbtp"],
                  "duration_seconds": receipt["duration_seconds"],
                  "priming_frames": receipt["restored_priming_frames"]}
        if getattr(args, "managed", False):
            result["artifact"] = _register_bgm_compose(args, project_path, receipt)
        return result

    raise AssertionError(f"Unknown bgm action: {args.bgm_action}")


def _register_bgm_compose(args, project_path, receipt):
    """PRD-004: register a standalone BGM compose output into the lifecycle."""
    import shutil
    from artifact_lifecycle import Lifecycle
    root = project_path(Path("."))
    core = Lifecycle.from_configuration(root, None)
    run = core.start_run({"workflow": "bgm-compose"})
    attempt = core.start_attempt(run["id"], "compose", "bgm-standalone")
    try:
        loop = project_path(args.loop)
        video = project_path(args.video)
        output = project_path(Path(receipt["output"]))
        work = core.work_path(attempt["id"])
        inputs = work / "inputs"
        with core.keep_lease(attempt["id"]):
            inputs.mkdir()
            dependencies = []
            for index, (source, logical) in enumerate(((loop, "sources/bgm-loop.caf"),
                                                       (video, "sources/preview-source.mp4"))):
                name = f"input-{index}{source.suffix.lower()}"
                snapshot = inputs / name
                shutil.copyfile(source, snapshot)
                registered = core.register(attempt["id"], snapshot, "capture",
                                           logical_path=logical)
                dependencies.append(registered["id"])
            receipt_file = work / "bgm-receipt.json"
            receipt_file.write_text(json.dumps(receipt, indent=2, sort_keys=True))
            receipt_artifact = core.register(attempt["id"], receipt_file, "producer-evidence",
                                             inputs=dependencies,
                                             logical_path="evidence/bgm-receipt.json")
            composed = core.register(attempt["id"], output, "preview",
                                     inputs=dependencies + [receipt_artifact["id"]],
                                     logical_path="preview/bgm-compose.mp4")
        core.finish_attempt(attempt["id"], "succeeded")
        return {"run_id": run["id"], "attempt_id": attempt["id"],
                "artifact_id": composed["id"], "receipt_artifact_id": receipt_artifact["id"]}
    except BaseException as error:
        resolved_output = project_path(Path(receipt["output"])).resolve()
        workspace = core.paths.workspace.resolve()
        if resolved_output.is_relative_to(workspace):
            resolved_output.unlink(missing_ok=True)
        terminal = ('cancelled' if isinstance(error, KeyboardInterrupt) else
                    'interrupted' if isinstance(error, SystemExit) else 'failed')
        try:
            core.finish_attempt(attempt["id"], terminal,
                                reason=str(error) or type(error).__name__)
        except Exception:
            pass
        raise


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

    binding = ppo_sub.add_parser("bind", help="Bind verified screenshot deliveries to deployed App Store IDs")
    assess = ppo_sub.add_parser("assess", help="Replay an App Analytics snapshot")
    for command in (binding, assess):
        command.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--config", type=Path)
        command.add_argument("--handoff", type=Path, required=True)
    binding.add_argument("--output", type=Path, required=True)
    binding.add_argument("--app-id", required=True)
    binding.add_argument("--asc-experiment-id", required=True)
    binding.add_argument("--treatment-id", action="append", required=True, metavar="LOCAL:REMOTE")
    assess.add_argument("--binding", type=Path, required=True)
    assess.add_argument("--snapshot", type=Path, required=True)
    assess.add_argument("--output", type=Path)
    assess.add_argument("--json", action="store_true", help="Emit JSON (default)")
    result = ppo_sub.add_parser("result", help="Save an observed experiment outcome for the next release")
    result.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
    result.add_argument("--config", type=Path)
    result.add_argument("--handoff", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--assessment", type=Path)
    for field in ("market", "change", "observation", "evidence"):
        result.add_argument("--" + field)
    result.add_argument("--decision", choices=("inconclusive", "keep-control", "use-treatment"))
    result.add_argument("--treatment", help="Selected treatment ID for use-treatment")

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

    ppo_reproduce = ppo_sub.add_parser("reproduce", help="Reproduce a winning variant into production deliveries (PRD-006)")
    ppo_reproduce.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
    ppo_reproduce.add_argument("--config", type=Path, help="Path to creative.config.json")
    ppo_reproduce.add_argument("--experiment", type=str, required=True, help="Experiment ID")
    choice = ppo_reproduce.add_mutually_exclusive_group(required=True)
    choice.add_argument("--variant", help="Explicitly selected treatment ID")
    choice.add_argument("--result", type=Path, help="Use the treatment selected in a recorded experiment result")
    ppo_reproduce.add_argument("--decision-basis", type=str, help="Human-readable decision basis recorded in receipts")
    ppo_reproduce.add_argument("--execute", action="store_true", help="Execute the reproduction (default is dry-run)")
    ppo_reproduce.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of the default review plan")

    bgm = cmd("bgm")
    bgm_sub = bgm.add_subparsers(dest="bgm_action", required=True)

    bgm_scan = bgm_sub.add_parser("scan", help="Scan installed Apple Loops and output a catalog")
    bgm_scan.add_argument("--output", type=Path, help="Output path for catalog JSON (default: stdout)")
    bgm_scan.add_argument("--library", type=Path, default=Path("/Library/Audio/Apple Loops"), help="Apple Loops library root")

    bgm_recommend = bgm_sub.add_parser("recommend", help="Score catalog entries against product context")
    bgm_recommend.add_argument("--catalog", type=Path, required=True, help="Path to catalog JSON from bgm scan")
    bgm_recommend.add_argument("--context", type=Path, help="Path to product-context JSON (or inline with --context-json)")
    bgm_recommend.add_argument("--context-json", type=str, help="Inline product-context JSON string")
    bgm_recommend.add_argument("--count", type=int, default=3, help="Maximum candidates to return (default 3)")
    bgm_recommend.add_argument("--output", type=Path, help="Output path for recommendations JSON (default: stdout)")

    bgm_compose = bgm_sub.add_parser("compose", help="Render background music onto a preview video")
    bgm_compose.add_argument("--loop", type=Path, required=True, help="Path to the chosen CAF loop")
    bgm_compose.add_argument("--video", type=Path, required=True, help="Path to the preview video")
    bgm_compose.add_argument("--output", type=Path, required=True, help="Output path for the composed MP4")
    bgm_compose.add_argument("--fade-in", type=float, default=0.35, help="Fade-in duration in seconds (default 0.35)")
    bgm_compose.add_argument("--fade-out-start", type=float, default=None, help="Fade-out start in seconds (default: video duration minus fade-out duration)")
    bgm_compose.add_argument("--fade-out-duration", type=float, default=1.5, help="Fade-out duration in seconds (default 1.5)")
    bgm_compose.add_argument("--target-lufs", type=float, default=-16.0, help="Target integrated LUFS (default -16)")
    bgm_compose.add_argument("--true-peak-ceiling", type=float, default=-1.0, help="True-peak ceiling in dBTP (default -1)")
    bgm_compose.add_argument("--receipt", type=Path, help="Optional path to write the Swift receipt JSON")
    bgm_compose.add_argument("--managed", action="store_true", help="Register the composed output in the artifact lifecycle (PRD-004)")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        res = run(args)
        if res is not None:
            if (args.command == "ppo" and args.ppo_action == "reproduce"
                    and not args.execute and not args.json):
                provenance = res["provenance"]
                print(f"Experiment: {provenance['experiment_id']} | Variant: {provenance['variant_id']}")
                print(f"Decision basis: {provenance['decision_basis']}")
                for group in res["scope"]["by_locale"]:
                    print(f"{group['locale']}: {', '.join(group['targets'])}")
                print(f"Planned deliveries: {res['scope']['planned_delivery_count']}")
            else:
                print(res if isinstance(res, str) else json.dumps(res, sort_keys=True, ensure_ascii=False, indent=2))
        # Ensure CI gates fail if validation reported FAIL
        if isinstance(res, dict) and res.get("status") == "FAIL":
            return 2
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
