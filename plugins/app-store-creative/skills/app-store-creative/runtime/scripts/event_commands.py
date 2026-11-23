"""CLI and content-addressed local records for In-App Events."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from pathlib import Path
import subprocess

import event_assessment
import event_handoff
import event_plan as rules
from record_primitives import canonical, safe_id
from studio_contract import atomic_json


def add_commands(parent):
    commands = parent.add_subparsers(dest="event_action", required=True)
    for name, flags in [
        ("plan", ("brief",)),
        ("validate", ("inventory", "routes")),
        ("handoff", ("validation",)),
        ("observe", ("snapshot",)),
        ("assess", ("store", "product")),
    ]:
        parser = commands.add_parser(name)
        parser.add_argument("--repo", type=Path, default=argparse.SUPPRESS)
        if name == "plan":
            parser.add_argument(
                "--expected-plan", help="Require the current plan to match this record SHA-256"
            )
        if name != "plan":
            parser.add_argument("--event", required=True)
        for flag in flags:
            parser.add_argument("--" + flag, type=Path, required=flag in ("brief", "snapshot"))


def checksum(data):
    return hashlib.sha256(canonical(data)).hexdigest()


def child(directory, name):
    path = directory / name
    rules.require(path.resolve() == path, f"Unexpected record symlink: {name}")
    return path


def read(directory, name):
    path = child(directory, name + ".json")
    data = rules.load(path)
    archived = child(directory, "records/" + checksum(data) + ".json")
    rules.require(rules.load(archived) == data, f"Unverified {name} record")
    return data


def save(directory, name, data):
    archived = child(directory, "records/" + checksum(data) + ".json")
    if archived.exists():
        rules.require(rules.load(archived) == data, "Archive digest mismatch")
    else:
        atomic_json(archived, data)
    atomic_json(child(directory, name + ".json"), data)


def validation(root, brief, paths, bound, now):
    findings = []
    assets = {}
    sources = {}

    def check(field, operation):
        try:
            return operation()
        except (ValueError, TypeError, KeyError, AttributeError, OSError, subprocess.SubprocessError) as exc:
            findings.append(
                rules.issue(
                    "invalid-input", field, str(exc), "verified evidence", "Correct and validate again"
                )
            )
            return None

    candidate = check("brief", lambda: rules.plan(root, brief))
    if candidate and candidate[0] != "propose":
        findings.append(rules.issue("candidate", "brief", candidate[0], "propose", "Resolve candidate first"))
    check("metadata", lambda: rules.fields(brief))
    check("measurement", lambda: event_assessment.policy(brief["measurement"]))
    for locale, row in brief.get("localizations", {}).items():
        assets[locale] = {}
        for slot in ("card", "details"):
            assets[locale][slot] = check(f"{locale}.{slot}", lambda: rules.media(root, row[slot], slot))
    inventory = None
    approval_available = None
    for name in ("inventory", "routes"):
        value = paths.get(name)
        if not value:
            findings.append(rules.issue("unknown", name, None, "current evidence", f"Supply --{name}"))
            continue
        path = rules.local(root, value)
        data = check(name, lambda: rules.load(path))
        if data is None:
            continue
        sources[name] = {"path": str(path.relative_to(root)), "sha256": checksum(data)}
        if name == "inventory":
            inventory = data
            approval_available = check(name, lambda: rules.calendar(brief, data, now, bound))
        else:
            check(name, lambda: rules.routes(root, brief, data))
    return dict(
        status="blocked" if findings else "ready",
        findings=findings,
        assets=assets,
        sources=sources,
        briefSha256=checksum(brief),
        approvalAvailable=approval_available,
        ruleVersion=1,
    ), inventory


def execute(args, root, project_path):
    action = args.event_action
    key = getattr(args, "event", None)
    try:
        brief = None
        if action == "plan":
            brief = rules.load(rules.local(root, project_path(args.brief)))
            key = brief["eventKey"]
        safe_id(key)
        directory = child(root, ".creative/events/" + key)
        directory.mkdir(parents=True, exist_ok=True)
        with child(directory, "event.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Concurrent event operation; reread current records") from None
            result = process(args, root, directory, brief)
        return dict(schemaVersion=1, eventKey=key, findings=[], artifacts={}) | result
    except (ValueError, TypeError, AttributeError, KeyError, OSError, subprocess.SubprocessError) as exc:
        return dict(
            schemaVersion=1,
            eventKey=key,
            status="blocked",
            artifacts={},
            findings=[
                rules.issue("invalid-input", action, str(exc), "valid input", "Correct the indicated input")
            ],
        )


def process(args, root, directory, brief):
    action = args.event_action
    now = datetime.now(timezone.utc)

    def output(name, record):
        data = {"schemaVersion": 1, "eventKey": directory.name, **record}
        save(directory, name, data)
        path = directory.relative_to(root) / "records" / (checksum(data) + ".json")
        return data | {"recordSha256": checksum(data), "artifacts": {name: str(path)}}

    if action == "plan":
        status, findings = rules.plan(root, brief)
        if child(directory, "plan.json").exists():
            saved = read(directory, "plan")
            if args.expected_plan:
                rules.require(checksum(saved) == args.expected_plan, "Plan changed since editing began")
            previous = saved["brief"]
            rules.require(
                all(previous[k] == brief[k] for k in ("appId", "projectId")),
                "Event key belongs to another app",
            )
        elif args.expected_plan:
            raise ValueError("Expected plan does not exist")
        return output("plan", dict(status=status, findings=findings, brief=brief))
    brief = read(directory, "plan")["brief"]
    binding = read(directory, "binding") if child(directory, "binding.json").exists() else {}
    if action == "validate":
        paths = {"inventory": args.inventory, "routes": args.routes}
        data, _ = validation(root, brief, paths, binding.get("eventId"), now)
        return output("validation", data)
    if action == "handoff":
        previous = read(directory, "validation")
        if args.validation:
            rules.require(
                rules.load(rules.local(root, args.validation)) == previous, "Validation has been superseded"
            )
        rules.require(previous["status"] == "ready", "Validation is blocked")
        paths = {k: v["path"] for k, v in previous["sources"].items()}
        fresh, inventory = validation(root, brief, paths, binding.get("eventId"), now)
        rules.require(
            all(previous.get(k) == v for k, v in fresh.items()), "Validation inputs changed; validate again"
        )
        data = event_handoff.handoff(brief, previous["assets"], inventory, binding.get("eventId"))
        return output(
            "handoff",
            dict(
                status="ready",
                validationSha256=checksum(previous),
                approvalAvailable=previous["approvalAvailable"],
                **data,
            ),
        )
    package = read(directory, "handoff")
    if action == "observe":
        snapshot = rules.load(rules.local(root, args.snapshot))
        rules.evidence(root, snapshot["evidence"])
        rules.require(snapshot["handoffSha256"] == checksum(package), "Handoff digest mismatch")
        result = event_handoff.reconcile(package, snapshot, binding)
        if child(directory, "observation.json").exists():
            previous = read(directory, "observation")
            old = rules.timestamp(previous["snapshot"]["observedAt"])
            current = rules.timestamp(snapshot["observedAt"])
            rules.require(
                current > old or (current == old and previous["snapshot"] == snapshot),
                "Stale or conflicting observation",
            )
        recorded = output("observation", result | {"snapshot": snapshot})
        if result.get("eventId"):
            save(
                directory,
                "binding",
                {
                    "schemaVersion": 1,
                    "appId": brief["appId"],
                    "eventId": result["eventId"],
                    "handoffSha256": checksum(package),
                },
            )
        return recorded
    rules.require(binding.get("handoffSha256") == checksum(package), "Observe the event before assessment")
    reports = [rules.load(rules.local(root, p)) if p else None for p in (args.store, args.product)]
    for report in reports:
        if report is not None:
            rules.evidence(root, report["evidence"])
    result = event_assessment.assess(package["brief"], binding, *reports)
    return output(
        "assessment", result | {"bindingSha256": checksum(binding), "handoffSha256": checksum(package)}
    )
