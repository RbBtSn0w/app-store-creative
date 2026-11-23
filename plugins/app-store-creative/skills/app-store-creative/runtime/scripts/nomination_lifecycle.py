"""Local nomination revisions, immutable plans, dispatch and ASC readback evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from artifact_lifecycle import require_human_authorization
import nomination_asc as asc
from record_primitives import canonical, digest, identifier, now, safe_id
from safe_staging import staged_file


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def brief_for(core, source):
    if not isinstance(source, dict) or type(source.get("schemaVersion", 1)) is not int or source.get("schemaVersion", 1) != 1:
        raise ValueError("unsupported_schema")
    if set(source) - {"target", "payload", "context", "evidence", "schemaVersion"}:
        raise ValueError("Unknown brief field")
    target = source.get("target", {})
    if not isinstance(target, dict) or set(target) - {"appIds", "profileRef"}:
        raise ValueError("Unknown nomination target field")
    apps = asc.strings(target.get("appIds", []), "appIds")
    if any(not re.fullmatch(r"[0-9]+", app) for app in apps):
        raise ValueError("Expected numeric Apple app IDs")
    profile = target.get("profileRef")
    if profile is not None:
        safe_id(profile)
    payload = asc.normalize(source.get("payload", {}))
    evidence = source.get("evidence", [])
    context = source.get("context", {})
    if not isinstance(context, dict) or not isinstance(evidence, list):
        raise ValueError("Invalid context or evidence")
    refs = set()
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Invalid evidence item")
        key = safe_id(item.get("id"))
        if key in refs:
            raise ValueError("Duplicate evidence ID")
        refs.add(key)
        if item.get("sourceKind") == "statement":
            require_human_authorization(item.get("actor"), item.get("text"))
            continue
        if item.get("sourceKind") not in {"file", "screenshot", "video", "releaseNotes"}:
            raise ValueError("Unknown evidence sourceKind")
        if item["sourceKind"] == "screenshot" and not all(item.get(k) for k in ("card", "locale", "device")):
            raise ValueError("Screenshot evidence requires card, locale and device")
        if item["sourceKind"] == "video" and "startMs" not in item:
            raise ValueError("Video evidence requires startMs and endMs")
        if "artifactId" in item:
            if "path" in item:
                raise ValueError("Select one artifactId or path per evidence item")
            artifact = core.verify_artifact(safe_id(item["artifactId"]))
            if core.source_eligibility_errors(artifact["id"]):
                raise ValueError("Evidence artifact has incomplete producer dependencies")
            resolved = core.object_path(artifact["sha256"])
            actual_digest = artifact["sha256"]
        else:
            path = Path(item["path"])
            resolved = (core.paths.project / path).resolve()
            if path.is_absolute() or not resolved.is_relative_to(core.paths.project) or not resolved.is_file():
                raise ValueError(f"Invalid evidence path: {key}")
            actual_digest = digest(resolved)
        if actual_digest != item.get("sha256"):
            raise ValueError(f"Evidence digest mismatch: {key}")
        if "startMs" in item or "endMs" in item:
            start, end = item.get("startMs"), item.get("endMs")
            if type(start) is not int or type(end) is not int or not 0 <= start < end:
                raise ValueError("Invalid video evidence range")
            duration = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                                "-of", "default=nw=1:nk=1", str(resolved)], timeout=30)
            if end > round(float(duration) * 1000):
                raise ValueError("Video evidence exceeds duration")
    claims = context.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("context.claims must be a list")
    for claim in claims:
        if (not isinstance(claim, dict) or not isinstance(claim.get("text"), str) or not claim["text"].strip()
                or not isinstance(claim.get("evidenceIds"), list) or not claim["evidenceIds"]
                or any(not isinstance(key, str) or key not in refs for key in claim["evidenceIds"])):
            raise ValueError("Missing claim evidence")
    return {"target": {"appIds": apps, "profileRef": profile}, "payload": payload,
            "context": context, "evidence": evidence}


def missing(brief):
    fields = [k for k in asc.REQUIRED if not brief["payload"].get(k)]
    fields.extend(k for k, v in brief["target"].items() if not v)
    if not brief["context"].get("claims"):
        fields.append("context.claims")
    return fields


class Nomination:
    """Operate on one nomination under the caller's lifecycle transaction."""

    def __init__(self, core, local_id):
        self.core = core
        self.id = safe_id(local_id)
        category = "nomination-events"
        directory = core._path(category, self.id, "00000001").parent
        self.events = []
        self.sequence = 0
        abandoned = set()
        for marker in (core.paths.workspace / "records/commit-abandonments").glob("*.json"):
            decision = core._read("commit-abandonments", marker.stem)
            ref = decision.get("record", {})
            if ref.get("category") == category and ref.get("id") == self.id:
                original = core._read("events", marker.stem)
                if (decision.get("status") != "ABANDONED" or original.get("record") != ref
                        or decision.get("event_sha256") != checksum(original)):
                    raise ValueError("Invalid nomination abandonment")
                abandoned.add(int(ref["suffix"]))
        for file in sorted(directory.glob("*.json")):
            row = core._read(category, self.id, file.stem)
            while self.sequence + 1 in abandoned:
                self.sequence += 1
            self.sequence += 1
            if (file.stem != f"{self.sequence:08d}" or row.get("seq") != self.sequence
                    or row["parent"] != self.parent or row.get("project_id") != core.config["project"]["id"]):
                raise ValueError("Nomination event chain integrity error")
            evidence = row["body"].get("evidenceDigest")
            if evidence:
                path = self.core.paths.publications / "nominations" / self.id / "evidence" / evidence
                if path.resolve() != path or digest(path) != evidence:
                    raise ValueError("Nomination response evidence integrity error")
            self.events.append(row)
        while self.sequence + 1 in abandoned:
            self.sequence += 1

    @property
    def parent(self):
        return checksum(self.events[-1]) if self.events else None

    def add(self, kind, body, actor="creative"):
        seq = self.sequence + 1
        data = {"id": self.id, "seq": seq, "parent": self.parent, "kind": kind, "body": body,
                "actor": actor, "project_id": self.core.config["project"]["id"]}
        self.events.append(self.core._record("nomination-events", data, f"{seq:08d}"))
        self.sequence = seq
        return body

    def latest(self, kind):
        return next((e["body"] for e in reversed(self.events) if e["kind"] == kind), {})

    def review(self):
        rev = self.latest("revision")
        if not rev:
            raise ValueError("Unknown local nomination")
        brief = rev["brief"]
        warnings = []
        start = brief["payload"].get("publishStartDate")
        if start and datetime.fromisoformat(start) < datetime.now(timezone.utc) + timedelta(days=14):
            warnings.append("Planned publication is less than 14 days away")
        prior = self.latest("verified").get("snapshot", {}).get("payload", {})
        expected = {**prior, **brief["payload"]}
        changes = {k: {"previous": prior.get(k), "proposed": v} for k, v in expected.items() if prior.get(k) != v}
        return {**rev, "localId": self.id, "missing": missing(brief), "warnings": warnings,
                "appleFields": expected, "changes": changes}

    def draft(self, source, base):
        brief = brief_for(self.core, source)
        old = self.latest("revision")
        sha = checksum(brief)
        if old and base is None:
            raise ValueError("An existing nomination requires --base")
        if old.get("revisionDigest") == sha and base in (sha, old.get("parentDigest")):
            return self.review()
        if base != old.get("revisionDigest"):
            raise ValueError("Revision conflict: reload review")
        if (self.latest("claim") or self.remote_id()) and old["brief"]["target"] != brief["target"]:
            raise ValueError("Cannot change target after dispatch")
        self.add("revision", {"brief": brief, "revisionDigest": sha, "parentDigest": base, "revision": old.get("revision", 0) + 1})
        return self.review()

    def pending(self):
        claim = self.latest("claim")
        if (claim and self.latest("verified").get("attempt") != claim["attempt"]
                and self.latest("rejected").get("attempt") != claim["attempt"]):
            return claim
        return {}

    def plan(self, action):
        rev = self.review()
        brief = brief_for(self.core, rev["brief"])
        if rev["missing"]:
            raise ValueError("Missing: " + ", ".join(rev["missing"]))
        if self.pending():
            raise ValueError("Outstanding attempt requires reconcile")
        previous = self.latest("verified").get("snapshot", {})
        if previous and previous["state"] != "DRAFT":
            raise ValueError("Remote nomination is not a draft")
        changes = {k: v for k, v in brief["payload"].items() if previous.get("payload", {}).get(k) != v}
        if action == "submit":
            if not previous or changes:
                raise ValueError("Save and verify the reviewed draft before submission")
            operation = "submit"
        elif previous:
            if not changes:
                return {"status": "no_change", "remoteId": previous["remoteId"]}
            operation = "update_draft"
        else:
            operation = "create_draft"
        body = {"operation": operation, "localId": self.id, "projectId": self.core.config["project"]["id"],
                "revisionDigest": rev["revisionDigest"], "revision": rev["revision"], "target": brief["target"], "changes": changes,
                "expected": {**previous.get("payload", {}), **brief["payload"]},
                "remoteId": previous.get("remoteId"), "baseline": previous}
        rejected = self.latest("rejected")
        if rejected:
            body["previousRejection"] = rejected["attempt"]
        asc.command(body)
        body["plan"] = self.id + "." + checksum(body)
        if body != self.latest("plan"):
            self.add("plan", body)
        return body

    def reviewed_plan(self, ref):
        plan = self.latest("plan")
        if plan.get("plan") != ref or self.review()["revision"] != plan["revision"]:
            raise ValueError("Stale nomination plan")
        return plan

    def authorize(self, ref, actor, reference):
        self.reviewed_plan(ref)
        require_human_authorization(actor, reference)
        return self.add("authorization", {"plan": ref, "actor": actor, "reference": reference}, actor)

    def claim(self, ref, baseline):
        plan = self.reviewed_plan(ref)
        if self.latest("authorization").get("plan") != ref:
            raise ValueError("Missing exact-plan authorization")
        old = self.latest("claim")
        if old.get("plan") == ref:
            return {"status": "already_claimed", "attempt": old["attempt"]}
        if self.pending():
            raise ValueError("Outstanding attempt")
        brief_for(self.core, self.review()["brief"])
        if baseline != plan["baseline"] or self.latest("verified").get("snapshot", {}) != baseline:
            raise ValueError("Remote baseline conflict")
        attempt = self.id + "." + identifier()
        self.add("claim", {"attempt": attempt, "plan": ref})
        return {"status": "claimed", "attempt": attempt, "argv": asc.command(plan), "environment": {"ASC_MAX_RETRIES": "0"}}

    def retain(self, raw):
        sha = hashlib.sha256(raw).hexdigest()
        root = self.core.paths.publications / "nominations" / self.id / "evidence"
        path = root / sha
        if path.resolve() != path:
            raise ValueError("Invalid nomination evidence path")
        root.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with staged_file(root) as staged:
                staged.stream.write(raw)
                staged.publish(path)
        if digest(path) != sha:
            raise ValueError("Corrupt nomination response evidence")
        return sha

    def remote_id(self):
        return self.latest("ack").get("remoteId") or self.latest("verified").get("snapshot", {}).get("remoteId")

    def observe(self, attempt, phase, raw, rid=None, observed_at=None):
        claim = self.latest("claim")
        if claim.get("attempt") != attempt:
            raise ValueError("Observation attempt mismatch")
        plan = self.latest("plan")
        sha = hashlib.sha256(raw).hexdigest()
        observed_at = observed_at or now()
        for row in reversed(self.events):
            body = row["body"]
            if body.get("attempt") == attempt and body.get("evidenceDigest") == sha and body.get("phase") == phase:
                return body
        if not self.pending():
            raise ValueError("Attempt is already verified")
        if phase == "rejection":
            errors = json.loads(raw).get("errors")
            if not isinstance(errors, list) or not errors or any(
                    str(error.get("status")) not in {"400", "401", "403", "404", "409", "422", "429"}
                    for error in errors):
                raise ValueError("Expected an explicit ASC rejection")
            if self.latest("ack").get("attempt") == attempt:
                raise ValueError("Cannot reject an acknowledged write")
            self.retain(raw)
            return self.add("rejected", {"attempt": attempt, "status": "rejected", "phase": phase,
                                         "evidenceDigest": sha, "observedAt": observed_at})
        remote_id = asc.resource(raw)["id"]
        expected_id = self.remote_id() or plan["remoteId"] or rid
        if expected_id and remote_id != expected_id:
            raise ValueError("Observation target mismatch")
        receipt = {"phase": phase, "attempt": attempt, "remoteId": remote_id, "evidenceDigest": sha, "observedAt": observed_at}
        if phase == "ack":
            self.retain(raw)
            return self.add("ack", receipt)
        if not expected_id:
            raise ValueError("Unknown create outcome requires explicit --remote-id")
        snapshot = asc.snapshot(raw, plan["target"], expected_id)
        last_conflict = self.latest("conflict")
        if last_conflict.get("attempt") == attempt:
            if datetime.fromisoformat(observed_at) < datetime.fromisoformat(last_conflict["observedAt"]):
                raise ValueError("Stale observation predates existing evidence")
            previous_date = last_conflict.get("modifiedAt")
            if previous_date and snapshot["modifiedAt"] and (
                    datetime.fromisoformat(snapshot["modifiedAt"]) < datetime.fromisoformat(previous_date)):
                raise ValueError("Stale remote modification date")
        self.retain(raw)
        receipt["modifiedAt"] = snapshot["modifiedAt"]
        expected_state = "SUBMITTED" if plan["operation"] == "submit" else "DRAFT"
        differences = [k for k, v in plan["expected"].items() if snapshot["payload"].get(k) != v]
        if snapshot["state"] != expected_state or differences:
            return self.add("conflict", {**receipt, "status": "conflict", "state": snapshot["state"], "fields": differences})
        return self.add("verified", {**receipt, "status": "verified", "snapshot": snapshot})

    def status(self):
        revision = self.review()
        pending = self.pending()
        last = self.latest("verified")
        result = last.get("status", "local_draft")
        if self.latest("claim") and self.latest("rejected").get("attempt") == self.latest("claim").get("attempt"):
            result = "rejected"
        if pending:
            result = "outcome_unknown"
            if self.latest("conflict").get("attempt") == pending["attempt"]:
                result = "conflict"
        return {"localId": self.id, "revisionDigest": revision["revisionDigest"], "remoteId": self.remote_id(),
                "lastReadback": self.latest("readback"),
                "status": result,
                "pending": pending, "lastVerified": last, "lastConflict": self.latest("conflict")}
