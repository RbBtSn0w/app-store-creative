#!/usr/bin/env python3
"""Stable command-line interface for the local App Store creative workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import creative_workflow as engine


def ns(**values):
    return argparse.Namespace(**values)


def run(args):
    root = args.repo.resolve()
    if args.command == "doctor": return engine.command_doctor(ns(root=root))
    if args.command == "init": return engine.command_init(ns(root=root, project=root.name))
    if args.command == "plan":
        run_id = args.run_id or engine.file_digest(args.release)[:16]
        return engine.command_plan(ns(root=root, manifest=args.release, run_id=run_id))
    if args.command == "status": return engine.command_status(ns(root=root, run_id=args.run_id))
    if args.command == "claim":
        return engine.command_claim(ns(root=root, run_id=args.run_id, task_id=args.task_id, owner=args.agent_id,
                                       ttl_seconds=args.ttl_seconds, reclaim_expired=args.reclaim_expired,
                                       release_claim=args.release_claim))
    if args.command == "complete":
        store = engine.Store(root); claim = engine.load_json(store.state / "claims" / f"{args.task_id}.json")
        if claim["run_id"] != args.run_id: raise engine.WorkflowError("claim does not belong to run")
        if claim["owner"] != args.agent_id: raise engine.WorkflowError("claim owner mismatch")
        supplied = engine.load_json(args.receipt)
        if supplied.get("task_id") not in (None, args.task_id): raise engine.WorkflowError("receipt task mismatch")
        return engine.command_complete(ns(root=root, task_id=args.task_id, token=claim["token"], producer_receipt=args.receipt))
    if args.command == "verify":
        planned = engine.command_plan(ns(root=root, manifest=args.release, run_id=args.run_id))
        return {"run_id": planned["run_id"], "verified": [engine.command_verify(ns(root=root, task_id=t)) for t in planned["task_ids"]]}
    if args.command == "approve":
        if args.confirm != "APPROVE": raise engine.WorkflowError("--confirm APPROVE is required")
        manifest_hash = engine.file_digest(args.input_manifest)
        planned = engine.command_plan(ns(root=root, manifest=args.release, run_id=None)); task_ids = planned["task_ids"]
        if args.stage == "upload":
            plan_document = engine.load_json(args.input_manifest)
            if not isinstance(plan_document.get("plans"), list): raise engine.WorkflowError("upload approval input must be an upload plan")
        approvals = [engine.command_approve(ns(root=root, task_id=t, stage=args.stage, approver=args.approved_by,
                                               input_sha256=manifest_hash)) for t in task_ids]
        return {"input_manifest_sha256": manifest_hash, "approvals": approvals}
    if args.command == "promote":
        if args.confirm_approved != "PROMOTE": raise engine.WorkflowError("--confirm-approved PROMOTE is required")
        planned = engine.command_plan(ns(root=root, manifest=args.release, run_id=None))
        return engine.promote_release(root, planned["run_id"], args.input_dir.resolve())
    if args.command == "upload-plan":
        task_ids = engine.command_plan(ns(root=root, manifest=args.release, run_id=None))["task_ids"]
        plans = [engine.command_upload_plan(ns(root=root, task_id=t)) for t in task_ids]
        body = {"schema_version": 1, "app": args.app, "version_id": args.version_id,
                "release_sha256": engine.file_digest(args.release), "plans": plans}
        engine.atomic_write(args.output, body)
        return {"output": str(args.output), "sha256": engine.file_digest(args.output), "count": len(plans)}
    if args.command == "upload":
        if args.confirm_approved != "UPLOAD": raise engine.WorkflowError("--confirm-approved UPLOAD is required")
        document = engine.load_json(args.plan)
        release_sha256 = engine.file_digest(args.release)
        if document.get("release_sha256") != release_sha256: raise engine.WorkflowError("upload plan is not bound to --release")
        plan_sha256 = engine.file_digest(args.plan)
        results = [engine.command_upload(ns(root=root, plan_id=p["plan_id"], execute=False, plan_sha256=plan_sha256)) for p in document["plans"]]
        return {"executed": False, "release_sha256": release_sha256, "results": results, "message": "validated dry-run; no ASC adapter installed"}
    if args.command == "audit":
        return {"scope": "local_integrity", "remote_verified": False, "app": args.app, "version_id": args.version_id,
                "release_sha256": engine.file_digest(args.release),
                **engine.command_audit(ns(root=root))}
    if args.command == "upgrade":
        result = engine.command_upgrade(ns(root=root))
        return {**result, "mode": "check"}
    raise AssertionError(args.command)


def build_parser():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    def cmd(name):
        x = sub.add_parser(name); x.add_argument("--repo", type=Path, required=True); return x
    d = cmd("doctor"); d.add_argument("--json", action="store_true")
    cmd("init")
    x = cmd("plan"); x.add_argument("--release", type=Path, required=True); x.add_argument("--run-id")
    x = cmd("status"); x.add_argument("--run-id", required=True)
    x = cmd("claim"); x.add_argument("--run-id", required=True); x.add_argument("--task-id", required=True); x.add_argument("--agent-id", required=True); x.add_argument("--ttl-seconds", type=int, default=1800); mode = x.add_mutually_exclusive_group(); mode.add_argument("--reclaim-expired", action="store_true"); mode.add_argument("--release", dest="release_claim", action="store_true")
    x = cmd("complete"); x.add_argument("--run-id", required=True); x.add_argument("--task-id", required=True); x.add_argument("--agent-id", required=True); x.add_argument("--receipt", type=Path, required=True)
    x = cmd("verify"); x.add_argument("--release", type=Path, required=True); x.add_argument("--run-id")
    x = cmd("approve"); x.add_argument("--release", type=Path, required=True); x.add_argument("--stage", choices=("design", "upload"), required=True); x.add_argument("--approved-by", required=True); x.add_argument("--input-manifest", type=Path, required=True); x.add_argument("--confirm", required=True)
    x = cmd("promote"); x.add_argument("--release", type=Path, required=True); x.add_argument("--input-dir", type=Path, required=True); x.add_argument("--confirm-approved", required=True)
    x = cmd("upload-plan"); x.add_argument("--release", type=Path, required=True); x.add_argument("--app", required=True); x.add_argument("--version-id", required=True); x.add_argument("--output", type=Path, required=True)
    x = cmd("upload"); x.add_argument("--release", type=Path, required=True); x.add_argument("--plan", type=Path, required=True); x.add_argument("--confirm-approved", required=True)
    x = cmd("audit"); x.add_argument("--release", type=Path, required=True); x.add_argument("--app", required=True); x.add_argument("--version-id", required=True)
    x = cmd("upgrade"); x.add_argument("--check", action="store_true", required=True)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        print(json.dumps(run(args), sort_keys=True, ensure_ascii=False)); return 0
    except engine.WorkflowError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
