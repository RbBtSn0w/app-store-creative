"""Commit intents bind production records without inventing successful execution."""
from contextlib import contextmanager, nullcontext
from datetime import datetime
import fcntl
import hashlib
import os
import platform
import stat


CATEGORIES = frozenset({"runs", "attempts", "attempt-leases", "artifacts", "imports",
    "input-dispositions", "candidates", "candidate-dispositions", "validations",
    "approvals", "deliveries", "publications", "remote-observations", "incidents", "commit-abandonments", "external-media", "external-retrievals", "external-archives", "publication-preparations", "observation-evidence"})


def sync_directory(directory):
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def before_commit(core, category, data, suffix):
    if category not in CATEGORIES:
        return
    from artifact_lifecycle import canonical
    actor = data.get("actor", data.get("owner"))
    if actor is None and data.get("attempt_id"):
        actor = core._read("attempts", data["attempt_id"], "started").get("owner")
    event = {"id": data["_commit_event_id"], "schema_version": 1, "created_at": data["created_at"],
        "kind": "record-commit-intent", "project_id": core.config.get("project", {}).get("id"),
        "record": {"category": category, "id": data["id"], "suffix": suffix,
                   "sha256": hashlib.sha256(canonical(data)).hexdigest()},
        "run_id": data.get("run_id", data["id"] if category == "runs" else None),
        "actor": actor, "executor": {"client_id": core._execution_id,
            "runtime": "app-store-creative", "python_version": platform.python_version(), "implementation": core._implementation_identity}}
    path = core._path("events", event["id"])
    core._write_path(path, event)
    sync_directory(path.parent)
    sync_directory(path.parent.parent)


@contextmanager
def read_lock(core):
    path = core.paths.workspace / "write.lock"
    if path.resolve() != path or path.is_symlink():
        raise ValueError("Unsafe history lock")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("History lock must be a regular file")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("History lock identity changed")
        fcntl.flock(stream, fcntl.LOCK_SH)
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("History lock identity changed")
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def verify(core, locked=False):
    from artifact_lifecycle import safe_id
    from configuration_layers import _read_regular, _document
    from inventory_lifecycle import files_without_links
    core._assert_paths()
    core._live_configuration()
    records = core.paths.workspace / "records"
    if not records.exists() and not records.is_symlink():
        return {"status": "PASS", "events": [], "untracked_records": [],
                "coverage": sorted(CATEGORIES), "record_count": 0, "duplicate_references": [],
                "reason": "Record commit evidence only; operation journals and remote readiness are separate gates"}
    with (nullcontext() if locked else read_lock(core)):
        core._live_configuration()
        files, links = files_without_links(records, strict=True)
        if links:
            raise ValueError("History contains unsafe record links")
        rows, covered, duplicates = [], set(), set()
        references, events, observed = set(), {}, {}
        for path in sorted(files):
            if path.parent != records / "events":
                continue
            event = _document(_read_regular(path))
            required = {"id", "schema_version", "created_at", "kind", "project_id", "record", "run_id", "actor", "executor"}
            if (set(event) != required or event["id"] != path.stem
                    or type(event["schema_version"]) is not int or event["schema_version"] != 1):
                raise ValueError("Invalid history event schema or identity")
            executor = event["executor"]
            if (not isinstance(executor, dict) or set(executor) != {"client_id", "runtime", "python_version", "implementation"}
                    or executor["runtime"] != "app-store-creative"
                    or not isinstance(executor["python_version"], str) or not executor["python_version"].strip()):
                raise ValueError("Invalid history executor identity")
            from runtime_identity import validate
            validate(executor["implementation"])
            safe_id(executor["client_id"])
            if event["actor"] is not None and (not isinstance(event["actor"], str) or not event["actor"].strip()):
                raise ValueError("Invalid history actor")
            if event["run_id"] is not None:
                safe_id(event["run_id"])
            if not isinstance(event["created_at"], str) or datetime.fromisoformat(event["created_at"]).tzinfo is None:
                raise ValueError("History event time must be timezone-aware")
            if event.get("kind") != "record-commit-intent" or event.get("project_id") != core.config.get("project", {}).get("id"):
                raise ValueError("History event scope differs")
            ref = event.get("record")
            if not isinstance(ref, dict) or set(ref) != {"category", "id", "suffix", "sha256"} or ref["category"] not in CATEGORIES:
                raise ValueError("Invalid history record reference")
            safe_id(ref["id"])
            if ref["suffix"] is not None:
                safe_id(ref["suffix"])
            if not isinstance(ref["sha256"], str) or len(ref["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in ref["sha256"]):
                raise ValueError("Invalid history record digest")
            target = core._path(ref["category"], ref["id"], ref["suffix"])
            name = target.relative_to(records).as_posix()
            reference = (name, ref["sha256"])
            if reference in references:
                duplicates.add(name)
            references.add(reference)
            events[event["id"]] = reference
            covered.add(name)
            raw = _read_regular(target, optional=True)
            if raw is None:
                state = "INCOMPLETE"
            else:
                body = _document(raw)
                observed[name] = (hashlib.sha256(raw).hexdigest(), body.get("_commit_event_id"))
                state = ("COMMITTED" if hashlib.sha256(raw).hexdigest() == ref["sha256"]
                         and body.get("id") == ref["id"] and type(body.get("schema_version")) is int
                         and body["schema_version"] == 1 and body.get("created_at") == event["created_at"]
                         and body.get("_commit_event_id") == event["id"] else "CHANGED")
            rows.append({"event_id": event["id"], "record": name, "status": state,
                         "created_at": event["created_at"], "actor": event.get("actor"),
                         "executor": event.get("executor"), "run_id": event.get("run_id")})
        committed = {row["event_id"] for row in rows if row["status"] == "COMMITTED"}
        for row in rows:
            current = observed.get(row["record"])
            if row["status"] != "CHANGED" or current is None:
                continue
            sha, event_id = current
            if (isinstance(event_id, str) and event_id in committed and events.get(event_id) == (row["record"], sha)
                    and events[row["event_id"]][1] != sha):
                row["status"] = "NOT_COMMITTED"
                row["committed_event_id"] = event_id
        for path in files:
            if path.parent != records / 'commit-abandonments':
                continue
            decision = core._read('commit-abandonments', path.stem)
            own_event = decision['_commit_event_id']
            if own_event not in committed:
                continue
            original_id = decision.get('event_id')
            original = next((row for row in rows if row['event_id'] == original_id), None)
            if (original is None or original['status'] != 'INCOMPLETE'
                    or decision.get('status') != 'ABANDONED'
                    or not isinstance(decision.get('actor'), str) or not decision['actor'].strip()
                    or not isinstance(decision.get('reason'), str) or not decision['reason'].strip()):
                raise ValueError('Invalid commit abandonment decision')
            event = core._read('events', original_id)
            from artifact_lifecycle import canonical
            if (decision.get('event_sha256') != hashlib.sha256(canonical(event)).hexdigest()
                    or decision.get('record') != event['record']
                    or record_references(core, event['record']['id'])):
                raise ValueError('Commit abandonment binding or references changed')
            original['status'] = 'ABANDONED'
            original['abandonment_id'] = decision['id']
        actual = {p.relative_to(records).as_posix() for p in files
                  if p.relative_to(records).parts[0] in CATEGORIES}
        untracked = sorted(actual - covered)
        passed = not untracked and not duplicates and all(row["status"] in ("COMMITTED", "NOT_COMMITTED", "ABANDONED") for row in rows)
        return {"status": "PASS" if passed else "FAIL", "events": rows,
                "untracked_records": untracked, "duplicate_references": sorted(duplicates),
                "record_count": len(actual), "coverage": sorted(CATEGORIES),
                "reason": "Record commit evidence only; operation journals and remote readiness are separate gates"}


JOURNAL_CATEGORIES = frozenset({'relocations', 'maintenance', 'storage-fences', 'storage-fence-releases'})


def journals(core):
    """Read existing control journals without changing snapshots or verifying effects."""
    from inventory_lifecycle import files_without_links
    from artifact_lifecycle import canonical
    core._assert_paths()
    core._live_configuration()
    root = core.paths.workspace / 'records'
    result = {'status': 'OBSERVED', 'execution_verified': False, 'entries': [],
              'coverage': sorted(JOURNAL_CATEGORIES),
              'reason': 'Recorded journal facts only; use operation-specific verification before recovery or maintenance'}
    if not root.exists() and not root.is_symlink():
        return result
    with read_lock(core):
        core._live_configuration()
        files, links = files_without_links(root, strict=True)
        if links:
            raise ValueError('Operation journals contain unsafe record links')
        for path in files:
            parts = path.relative_to(root).parts
            if parts[0] not in JOURNAL_CATEGORIES:
                continue
            if path.suffix != '.json' or len(parts) not in (2, 3):
                raise ValueError('Unknown operation journal record layout')
            identity = path.parent.name if len(parts) == 3 else path.stem
            suffix = path.stem if len(parts) == 3 else None
            data = core._read(parts[0], identity, suffix)
            created = data.get('created_at')
            if not isinstance(created, str) or datetime.fromisoformat(created).tzinfo is None:
                raise ValueError('Operation journal requires timezone-aware creation time')
            result['entries'].append({'category': parts[0], 'id': identity, 'record': '/'.join(parts),
                'created_at': created, 'operation': data.get('operation'), 'recorded_status': data.get('status'),
                'actor': data.get('actor'), 'sha256': hashlib.sha256(canonical(data)).hexdigest()})
        result['entries'].sort(key=lambda row: (row['created_at'], row['record']))
    return result


def record_references(core, identity):
    """Conservatively protect any business record referring to the missing identity."""
    from configuration_layers import _read_regular, _document
    from inventory_lifecycle import files_without_links
    files, links = files_without_links(core.paths.workspace / 'records', strict=True)
    if links:
        raise ValueError('Commit recovery contains unsafe record links')
    def refers(value):
        if isinstance(value, dict):
            return any(refers(item) for item in value.values())
        if isinstance(value, list):
            return any(refers(item) for item in value)
        return value == identity
    return any(refers({key: value for key, value in _document(_read_regular(path)).items()
                       if key not in ('id', '_commit_event_id')}) for path in files
               if path.relative_to(core.paths.workspace / 'records').parts[0] in CATEGORIES - {'commit-abandonments'})


def abandon(core, event_id, actor, reason):
    from artifact_lifecycle import canonical
    if any(not isinstance(value, str) or not value.strip() for value in (actor, reason)):
        raise ValueError('Commit abandonment requires actor and reason')
    with core.transaction():
        audit = verify(core, locked=True)
        row = next((item for item in audit['events'] if item['event_id'] == event_id), None)
        if row is None or row['status'] != 'INCOMPLETE':
            raise ValueError('Only a missing commit target can be explicitly abandoned')
        event = core._read('events', event_id)
        if record_references(core, event['record']['id']):
            raise ValueError('Missing commit is referenced by existing business records')
        return core._record('commit-abandonments', {'id': event_id, 'event_id': event_id,
            'event_sha256': hashlib.sha256(canonical(event)).hexdigest(), 'record': event['record'],
            'status': 'ABANDONED', 'actor': actor, 'reason': reason})
