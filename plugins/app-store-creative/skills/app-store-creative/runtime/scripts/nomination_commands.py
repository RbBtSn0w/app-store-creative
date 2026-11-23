"""CLI orchestration for local nomination records and explicitly authorized ASC operations."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from artifact_lifecycle import Lifecycle
from configuration_layers import _read_regular
import nomination_asc as asc
from nomination_lifecycle import Nomination
from operation_history import read_lock
from record_primitives import identifier, safe_id


def add_arguments(parser):
    subs = parser.add_subparsers(dest="action", required=True)
    for name in ("draft", "review", "plan", "authorize", "claim", "execute", "observe", "status", "reconcile"):
        p = subs.add_parser(name)
        p.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
        if name in ("draft", "review", "status", "plan", "reconcile"):
            p.add_argument("--id", required=name != "draft")
        if name == "draft":
            p.add_argument("--brief", type=Path, required=True)
            p.add_argument("--base")
        if name == "review":
            p.add_argument("--format", choices=("json", "markdown"), default="json")
        if name == "plan":
            p.add_argument("--action", dest="operation", choices=("save-draft", "submit"), required=True)
        if name in ("authorize", "claim", "execute"):
            p.add_argument("--plan", required=True)
        if name == "authorize":
            p.add_argument("--actor", required=True)
            p.add_argument("--human-reference", required=True)
        if name == "observe":
            p.add_argument("--attempt", required=True)
            p.add_argument("--response", type=Path, required=True)
            p.add_argument("--scope", type=Path, required=True)
        if name == "reconcile":
            p.add_argument("--remote-id")
            p.add_argument("--accept-baseline", action="store_true",
                           help="Bind the explicitly selected draft or adopt its reviewed external changes")


def preflight(plan):
    argv = asc.command(plan)
    help_result = subprocess.run([*argv[:5], "--help"], capture_output=True, text=True,
                                 check=False, timeout=15)
    switches = {"--submitted", "--output", "--app" if plan["operation"] == "create_draft" else "--id"}
    switches.update("--" + asc.FLAGS[key] for key in plan["changes"])
    available = {line.split()[0] for line in (help_result.stdout + help_result.stderr).splitlines()
                 if line.strip().startswith("--")}
    if help_result.returncode or switches - available:
        raise ValueError("ASC lacks nomination options: " + ", ".join(sorted(switches - available)))
    target = plan["target"]
    event_ids = set(plan["expected"].get("inAppEventIds", []))
    found = set()
    for app in target["appIds"]:
        item = json.loads(asc.read_asc(target, "apps", "view", "--id", app))["data"]
        if item["type"] != "apps" or item["id"] != app:
            raise ValueError("ASC app identity mismatch")
        if event_ids:
            rows = json.loads(asc.read_asc(target, "app-events", "list", "--app", app, "--paginate"))["data"]
            found.update(row["id"] for row in rows if row["type"] == "appEvents")
    if event_ids - found:
        raise ValueError("In-app event does not belong to the target apps")
    rid = plan["remoteId"]
    return asc.snapshot(asc.view(target, rid), target, rid) if rid else {}


def prepare_plan(core, lid, operation):
    with read_lock(core):
        journal = Nomination(core, lid)
        parent = journal.parent
        previous = journal.baseline() or None
        target = journal.review()["brief"]["target"]
        if journal.pending():
            raise ValueError("Outstanding attempt requires reconcile")
    if previous:
        rid = previous["remoteId"]
        live = asc.snapshot(asc.view(target, rid), target, rid)
        if previous != live:
            fields = sorted(key for key in live["payload"].keys() | previous["payload"].keys()
                            if live["payload"].get(key) != previous["payload"].get(key))
            return {"status": "conflict", "remoteId": rid, "fields": fields, "state": live["state"],
                    "nextAction": "reconcile"}
    with core.transaction():
        journal = Nomination(core, lid)
        if journal.parent != parent:
            raise ValueError("Local state changed during planning")
        return journal.plan(operation)


def dispatch(core, lid, ref, run):
    with read_lock(core):
        journal = Nomination(core, lid)
        plan = journal.reviewed_plan(ref)
        if journal.latest("authorization").get("plan") != ref:
            raise ValueError("Missing exact-plan authorization")
        if journal.latest("claim").get("plan") == ref:
            return {"status": "already_claimed", "attempt": journal.latest("claim")["attempt"]}
    baseline = preflight(plan)
    with core.transaction():
        handoff = Nomination(core, lid).claim(ref, baseline)
    if not run or handoff["status"] != "claimed":
        return handoff
    attempt = handoff["attempt"]
    try:
        proc = subprocess.run(handoff["argv"], capture_output=True, check=False, timeout=90,
                              env={**os.environ, **handoff["environment"]})
        if proc.returncode:
            for raw in (proc.stdout, proc.stderr):
                try:
                    with core.transaction():
                        return Nomination(core, lid).observe(attempt, "rejection", raw)
                except (ValueError, AttributeError, UnicodeError):
                    continue
            return {"status": "outcome_unknown", "attempt": attempt, "exitCode": proc.returncode,
                    "nextAction": "reconcile"}
        with core.transaction():
            ack = Nomination(core, lid).observe(attempt, "ack", proc.stdout)
        raw = asc.view(plan["target"], ack["remoteId"])
        with core.transaction():
            return Nomination(core, lid).observe(attempt, "view", raw)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return {"status": "outcome_unknown", "attempt": attempt, "nextAction": "reconcile",
                "reason": type(exc).__name__}


def reconcile(core, lid, args):
    with read_lock(core):
        journal = Nomination(core, lid)
        target = journal.review()["brief"]["target"]
        pending = journal.pending()
        bound = journal.remote_id()
        parent = journal.parent
    if bound and args.remote_id and args.remote_id != bound:
        raise ValueError("Cannot rebind a nomination to another remote ID")
    rid = bound or args.remote_id
    if not target["profileRef"] or not target["appIds"]:
        raise ValueError("Missing ASC target")
    if not rid:
        candidates = set()
        for app in target["appIds"]:
            for state in ("DRAFT", "SUBMITTED", "ARCHIVED"):
                response = asc.read_asc(target, "nominations", "list", "--app", app, "--status", state, "--paginate")
                candidates.update(r["id"] for r in json.loads(response)["data"] if r["type"] == "nominations")
        return {"status": "unverified", "candidateIds": sorted(candidates), "nextAction": "review an explicit remote ID"}
    raw = asc.view(target, safe_id(rid))
    snap = asc.snapshot(raw, target, rid)
    with core.transaction():
        journal = Nomination(core, lid)
        if journal.parent != parent:
            raise ValueError("Local state changed during reconciliation")
        if pending and (bound or args.accept_baseline):
            result = journal.observe(pending["attempt"], "view", raw, rid)
            if result.get("status") != "conflict" or not args.accept_baseline or snap["state"] != "DRAFT":
                return result
            return journal.add("baseline-adopted", {"status": "baseline_adopted", "remoteId": rid,
                               "snapshot": snap, "supersededAttempt": pending["attempt"],
                               "evidenceDigest": result["evidenceDigest"], "observedAt": result["observedAt"]})
        previous = journal.baseline()
        if not args.accept_baseline or snap["state"] != "DRAFT":
            fact = {"remoteId": rid, "snapshot": snap, "evidenceDigest": journal.retain(raw)}
            last = journal.latest("readback")
            if last.get("evidenceDigest") != fact["evidenceDigest"]:
                journal.add("readback", {**fact, "observedAt": datetime.now(timezone.utc).isoformat()})
            return {"status": "observed" if previous == snap else "unverified", **fact, "baseline": previous}
        return journal.add("verified", {"status": "verified", "remoteId": rid, "snapshot": snap,
                                        "attempt": journal.latest("verified").get("attempt"),
                                        "observedAt": datetime.now(timezone.utc).isoformat(),
                                        "evidenceDigest": journal.retain(raw)})


def execute(args, root, project_path):
    core = Lifecycle.from_configuration(root)
    ref = getattr(args, "plan", None) or getattr(args, "attempt", None)
    lid = ref.partition(".")[0] if ref else (args.id or identifier())
    action = args.action
    if action in ("claim", "execute"):
        if os.environ.get("CI", "").lower() in {"true", "1", "yes"}:
            raise ValueError("Nomination dispatch requires an interactive publisher outside CI")
        result = dispatch(core, lid, ref, action == "execute")
    elif action == "plan":
        result = prepare_plan(core, lid, args.operation)
    elif action == "reconcile":
        result = reconcile(core, lid, args)
    else:
        lock = read_lock(core) if action in ("review", "status") else core.transaction()
        with lock:
            journal = Nomination(core, lid)
            if action == "draft":
                source = json.loads(_read_regular(project_path(args.brief)))
                result = journal.draft(source, args.base)
            elif action == "review":
                result = journal.review()
                if args.format == "markdown":
                    brief = result["brief"]
                    return "\n\n".join(["# " + brief["payload"].get("name", "Featuring nomination"),
                                        brief["payload"].get("description", ""), "## Apple fields",
                                        json.dumps({**brief["target"], **result["appleFields"]}, ensure_ascii=False, indent=2),
                                        "## Changes", json.dumps(result["changes"], ensure_ascii=False, indent=2),
                                        "## Supporting evidence", json.dumps([brief["context"], brief["evidence"]], ensure_ascii=False),
                                        "## Missing", ", ".join(result["missing"]) or "None", *result["warnings"]])
            elif action == "status":
                result = journal.status()
            elif action == "authorize":
                result = journal.authorize(ref, args.actor, args.human_reference)
            else:
                scope = json.loads(_read_regular(project_path(args.scope)))
                plan = journal.latest("plan")
                expected = {"projectId": core.config["project"]["id"], **plan["target"],
                            "attemptId": ref, "planDigest": plan["plan"].partition(".")[2]}
                if any(scope.get(k) != v for k, v in expected.items()) or scope.get("phase") not in ("ack", "view", "rejection"):
                    raise ValueError("Observation scope mismatch")
                seen = datetime.fromisoformat(asc.date(scope.get("observedAt")))
                claimed_at = next(e["created_at"] for e in reversed(journal.events) if e["kind"] == "claim")
                if not datetime.fromisoformat(claimed_at) <= seen <= datetime.now(timezone.utc):
                    raise ValueError("Observation outside attempt time window")
                result = journal.observe(ref, scope["phase"], _read_regular(project_path(args.response)),
                                         observed_at=seen.isoformat())
    return {"schemaVersion": 1, **result}
