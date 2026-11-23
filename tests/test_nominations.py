import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime"
sys.path.insert(0, str(RUNTIME / "scripts"))
import nomination_asc as asc

FAKE = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["FAKE_ASC_DIR"])
args = sys.argv[1:]
assert args[:2] == ["--profile", "team"]
group, cmd = args[2:4]
def flag(key):
    return args[args.index(key) + 1]
if "--help" in args:
    for flag_name in ("name", "type", "description", "publish-start-date", "app", "id", "submitted", "output"):
        print("  --" + flag_name + " test option")
    sys.exit()
if group == "apps":
    print(json.dumps({"data": {"type": "apps", "id": flag("--id")}}))
    sys.exit()
assert group == "nominations"
state = root / "remote.json"
if cmd == "create":
    assert not state.exists()
    data = {"id": "remote1", "type": "nominations", "attributes": {},
            "relationships": {"relatedApps": {"data": [{"type": "apps", "id": flag("--app")}]},
                              "inAppEvents": {"data": []}, "supportedTerritories": {"data": []}}}
else:
    data = json.loads(state.read_text())
if cmd in ("create", "update"):
    assert os.environ["ASC_MAX_RETRIES"] == "0"
    attrs = data["attributes"]
    for name, arg in [("name", "--name"), ("description", "--description"), ("type", "--type"),
                      ("publishStartDate", "--publish-start-date")]:
        if arg in args:
            attrs[name] = flag(arg).removeprefix("@") if flag(arg).startswith("@@") else flag(arg)
    attrs["state"] = "SUBMITTED" if "--submitted=true" in args else "DRAFT"
    with (root / "writes").open("a") as stream:
        print(cmd, attrs["state"], file=stream)
    state.write_text(json.dumps(data))
    if (root / "drop").exists():
        sys.exit(1)
if cmd == "list":
    print(json.dumps({"data": [data] if data["attributes"]["state"] == flag("--status") else []}))
else:
    print(json.dumps({"data": data}))
'''


class NominationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.project = self.root / "product with spaces"
        self.project.mkdir()
        shutil.copyfile(RUNTIME / "assets/templates/creative.config.json", self.project / "creative.config.json")
        cli = self.root / "asc"
        cli.write_text(FAKE.replace("#!/usr/bin/env python3", "#!" + sys.executable))
        cli.chmod(0o700)
        self.env = dict(os.environ, PATH=str(self.root) + ":" + os.environ["PATH"], CI="false",
                        FAKE_ASC_DIR=str(self.root), APP_STORE_CREATIVE_PYTHON=sys.executable)
        self.brief = {"target": {"profileRef": "team", "appIds": ["123"]},
                      "payload": {"name": "Launch", "description": "@env:KEEP_LITERAL",
                                  "type": "APP_LAUNCH", "publishStartDate": "2027-05-01T08:00:00+08:00"},
                      "context": {"claims": [{"text": "New launch", "evidenceIds": ["note"]}]},
                      "evidence": [{"id": "note", "sourceKind": "statement", "actor": "author", "text": "New launch"}]}

    def cli(self, *args, fail=False):
        process = subprocess.run([str(RUNTIME / "scripts/app-store-creative"), "nomination", *args],
                                 cwd=self.root, env=self.env, text=True, capture_output=True)
        if fail:
            self.assertNotEqual(process.returncode, 0, process.stdout)
        else:
            self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        return json.loads(process.stdout or process.stderr)

    def call(self, *args, **kwargs):
        return self.cli("--repo", str(self.project), *args, **kwargs)

    def draft(self, *args):
        (self.project / "brief.json").write_text(json.dumps(self.brief))
        return self.cli("draft", "--repo", str(self.project), "--brief", "brief.json", *args)

    def authorize(self, lid, action):
        plan = self.call("plan", "--action", action, "--id", lid)["plan"]
        self.call("authorize", "--plan", plan, "--actor", "owner", "--human-reference", "reviewed in chat")
        return plan

    def test_update_submit_lost_response_and_recovery(self):
        rev = self.draft()
        lid = rev["localId"]
        plan = self.authorize(lid, "save-draft")
        saved = self.call("execute", "--plan", plan)
        self.assertEqual(saved["snapshot"]["payload"]["description"], "@env:KEEP_LITERAL")
        self.assertEqual(self.call("plan", "--id", lid, "--action", "save-draft")["status"], "no_change")
        self.brief["payload"] = {}
        self.brief["payload"]["description"] = "Updated 中文\nsecond line"
        self.draft("--id", lid, "--base", rev["revisionDigest"])
        self.call("execute", "--plan", plan, fail=True)
        updated = self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        self.assertEqual(updated["remoteId"], saved["remoteId"])
        submit = self.authorize(lid, "submit")
        (self.root / "drop").touch()
        self.assertEqual(self.call("execute", "--plan", submit, fail=True)["status"], "outcome_unknown")
        self.assertEqual(self.call("execute", "--plan", submit)["status"], "already_claimed")
        recovered = self.call("reconcile", "--id", lid)
        self.assertEqual(recovered["snapshot"]["state"], "SUBMITTED")
        self.assertEqual(self.call("status", "--id", lid)["lastVerified"],
                         {k: v for k, v in recovered.items() if k != "schemaVersion"})
        self.assertEqual((self.root / "writes").read_text().splitlines(),
                         ["create DRAFT", "update DRAFT", "update SUBMITTED"])

    def test_unknown_create_requires_explicit_binding(self):
        lid = self.draft()["localId"]
        plan = self.authorize(lid, "save-draft")
        (self.root / "drop").touch()
        self.call("execute", "--plan", plan, fail=True)
        self.assertEqual(self.call("reconcile", "--id", lid, fail=True)["candidateIds"], ["remote1"])
        self.call("reconcile", "--id", lid, "--remote-id", "remote1", fail=True)
        self.assertEqual(self.call("reconcile", "--id", lid, "--remote-id", "remote1",
                                   "--accept-baseline")["status"], "verified")
        self.assertEqual((self.root / "writes").read_text(), "create DRAFT\n")

    def test_accept_conflicting_draft_after_lost_update(self):
        rev = self.draft()
        lid = rev["localId"]
        saved = self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        self.brief["payload"] = {"description": "Revised"}
        self.draft("--id", lid, "--base", rev["revisionDigest"])
        plan = self.authorize(lid, "save-draft")
        (self.root / "drop").touch()
        self.call("execute", "--plan", plan, fail=True)
        file = self.root / "remote.json"
        remote = json.loads(file.read_text())
        remote["attributes"]["name"] = "Web edit"
        file.write_text(json.dumps(remote))
        self.assertEqual(self.call("reconcile", "--id", lid, fail=True)["status"], "conflict")
        self.assertEqual(self.call("reconcile", "--id", lid, "--accept-baseline")["status"], "baseline_adopted")
        status = self.call("status", "--id", lid)
        self.assertFalse(status["pending"])
        self.assertEqual(status["lastVerified"]["attempt"], saved["attempt"])
        self.assertEqual(self.call("plan", "--id", lid, "--action", "submit")["operation"], "submit")

    def test_incompatible_remote_baseline_keeps_prior_snapshot(self):
        rev = self.draft()
        lid = rev["localId"]
        saved = self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        file = self.root / "remote.json"
        remote = json.loads(file.read_text())
        remote["attributes"].update(publishStartDate="2027-04-28T00:00:00Z",
                                    publishEndDate="2027-04-30T00:00:00Z")
        file.write_text(json.dumps(remote))
        failure = self.call("reconcile", "--id", lid, "--accept-baseline", fail=True)
        self.assertIn("publishEndDate", failure["error"])
        self.assertEqual(self.call("status", "--id", lid)["baseline"], saved["snapshot"])
        self.assertEqual(self.call("review", "--id", lid)["revisionDigest"], rev["revisionDigest"])
        self.brief["payload"].pop("publishStartDate")
        self.draft("--id", lid, "--base", rev["revisionDigest"])
        self.assertEqual(self.call("reconcile", "--id", lid, "--accept-baseline")["status"], "verified")

    def test_invalid_partial_revision_preserves_known_digest(self):
        rev = self.draft()
        lid = rev["localId"]
        self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        file = self.root / "remote.json"
        remote = json.loads(file.read_text())
        remote["attributes"]["publishEndDate"] = "2027-05-02T00:00:00Z"
        file.write_text(json.dumps(remote))
        self.call("reconcile", "--id", lid, "--accept-baseline")
        self.brief["payload"] = {"publishStartDate": "2027-05-03T00:00:00Z"}
        (self.project / "brief.json").write_text(json.dumps(self.brief))
        self.call("draft", "--brief", "brief.json", "--id", lid, "--base", rev["revisionDigest"], fail=True)
        self.assertEqual(self.call("status", "--id", lid)["revisionDigest"], rev["revisionDigest"])
        self.brief["payload"] = {"description": "Corrected"}
        self.draft("--id", lid, "--base", rev["revisionDigest"])

    def test_external_edit_detected_before_write(self):
        lid = self.draft()["localId"]
        self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        plan = self.authorize(lid, "submit")
        file = self.root / "remote.json"
        remote = json.loads(file.read_text())
        remote["attributes"]["description"] = "Edited on web"
        file.write_text(json.dumps(remote))
        self.assertIn("conflict", self.call("execute", "--plan", plan, fail=True)["error"])
        self.assertEqual((self.root / "writes").read_text(), "create DRAFT\n")

    def test_claim_concurrency_and_scope(self):
        lid = self.draft()["localId"]
        plan = self.authorize(lid, "save-draft")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: self.call("claim", "--plan", plan), range(2)))
        self.assertEqual(sum("argv" in r for r in receipts), 1)
        self.assertEqual(receipts[0]["attempt"], receipts[1]["attempt"])
        (self.project / "wrong.json").write_text("{}")
        self.call("observe", "--attempt", receipts[0]["attempt"], "--response", "wrong.json",
                  "--scope", "wrong.json", fail=True)

    def test_evidence_and_incomplete_draft(self):
        text = self.project / "notes.txt"
        text.write_text("new functionality")
        self.brief["evidence"] = [{"id": "note", "sourceKind": "file", "path": "notes.txt",
                                   "sha256": hashlib.sha256(text.read_bytes()).hexdigest()}]
        del self.brief["payload"]["publishStartDate"]
        rev = self.draft()
        self.assertIn("publishStartDate", rev["missing"])
        self.call("plan", "--id", rev["localId"], "--action", "save-draft", fail=True)
        text.write_text("changed")
        self.assertIn("digest mismatch", self.call("plan", "--id", rev["localId"], "--action", "save-draft", fail=True)["error"])

    def test_mixed_case_enum_values_are_canonicalized(self):
        self.brief["payload"].update(type="app_Launch", deviceFamilies=["iPhone", "IPHONE"])
        fields = self.draft()["appleFields"]
        self.assertEqual((fields["type"], fields["deviceFamilies"]), ("APP_LAUNCH", ["IPHONE"]))

    def test_invalid_payloads(self):
        for bad in [{"locales": "en-US"}, {"type": "UPDATE"}, {"publishStartDate": "2027-05-01"},
                    {"deviceFamilies": ["IOS"]}, {"preOrderEnabled": 1}, {"supportedTerritories": ["US"]},
                    {"supplementalMaterialsUris": ["https://user:pw@example.org/private"]},
                    {"hasInAppEvents": False, "inAppEventIds": ["123"]}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                asc.normalize(bad)

    def test_rejection_can_replan_but_ambiguous_error_cannot(self):
        rev = self.draft()
        lid = rev["localId"]
        plan = self.authorize(lid, "save-draft")
        attempt = self.call("claim", "--plan", plan)["attempt"]
        from datetime import datetime, timezone
        scope = {"phase": "rejection", "projectId": "habit-flow", **self.brief["target"], "attemptId": attempt,
                 "planDigest": plan.split(".")[1], "observedAt": datetime.now(timezone.utc).isoformat()}
        (self.project / "scope.json").write_text(json.dumps(scope))
        def report(code, fail):
            (self.project / "response.json").write_text(json.dumps({"errors": [{"status": str(code)}]}))
            return self.call("observe", "--attempt", attempt, "--scope", "scope.json",
                             "--response", "response.json", fail=fail)
        report(503, True)
        self.assertEqual(self.call("status", "--id", lid)["status"], "outcome_unknown")
        self.assertEqual(report(403, True)["status"], "rejected")
        next_plan = self.call("plan", "--id", lid, "--action", "save-draft")["plan"]
        self.assertNotEqual(plan, next_plan)
        self.call("execute", "--plan", next_plan, fail=True)
        self.assertFalse((self.root / "writes").exists())

    def test_readback_tampering_and_aba_revision(self):
        rev = self.draft()
        lid = rev["localId"]
        plan = self.authorize(lid, "save-draft")
        self.brief["payload"]["name"] = "temporary"
        other = self.draft("--id", lid, "--base", rev["revisionDigest"])
        self.brief["payload"]["name"] = "Launch"
        self.draft("--id", lid, "--base", other["revisionDigest"])
        self.call("claim", "--plan", plan, fail=True)
        result = self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        evidence = self.project / "creative-publications/nominations" / lid / "evidence" / result["evidenceDigest"]
        evidence.write_bytes(b"{}")
        self.assertIn("integrity", self.call("status", "--id", lid, fail=True)["error"])

    def test_remote_adoption_and_web_edit(self):
        lid = self.draft()["localId"]
        self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        file = self.root / "remote.json"
        remote = json.loads(file.read_text())
        remote["attributes"]["locales"] = ["fr-FR"]
        file.write_text(json.dumps(remote))
        self.call("reconcile", "--id", lid, "--accept-baseline")
        self.assertEqual(self.call("status", "--id", lid)["pending"], {})
        self.assertEqual(self.call("review", "--id", lid)["appleFields"]["locales"], ["fr-FR"])
        plan = self.authorize(lid, "submit")
        self.assertEqual(self.call("execute", "--plan", plan)["snapshot"]["state"], "SUBMITTED")

    def test_incomplete_relationships_and_unsupported_schema(self):
        lid = self.draft()["localId"]
        self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        raw = json.loads((self.root / "remote.json").read_text())
        raw["relationships"]["relatedApps"]["links"] = {"next": "next-page"}
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            asc.snapshot(json.dumps({"data": raw}), self.brief["target"], "remote1")
        self.brief["schemaVersion"] = True
        (self.project / "brief.json").write_text(json.dumps(self.brief))
        self.assertIn("unsupported_schema", self.call("draft", "--brief", "brief.json", fail=True)["error"])

    def test_two_stories_types_and_material_scope(self):
        ids = set()
        for kind in ("APP_LAUNCH", "APP_ENHANCEMENTS", "NEW_CONTENT"):
            self.brief["payload"]["type"] = kind
            ids.add(self.draft()["localId"])
        self.assertEqual(len(ids), 3)
        file = self.root / "outside"
        file.write_text("secret")
        (self.project / "link").symlink_to(file)
        self.brief["evidence"] = [{"id": "note", "sourceKind": "file", "path": "link",
                                   "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}]
        (self.project / "brief.json").write_text(json.dumps(self.brief))
        self.assertIn("Invalid evidence path", self.call("draft", "--brief", "brief.json", fail=True)["error"])

    def test_omission_explicit_clear_and_registry(self):
        schema = json.loads((RUNTIME / "schemas/nomination-brief.v1.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["payload"]["properties"]), set(asc.FLAGS))
        rev = self.draft()
        lid = rev["localId"]
        self.call("execute", "--plan", self.authorize(lid, "save-draft"))
        file = self.root / "remote.json"
        data = json.loads(file.read_text())
        data["attributes"]["locales"] = ["en-US"]
        file.write_text(json.dumps(data))
        self.call("reconcile", "--id", lid, "--accept-baseline")
        self.brief["payload"]["locales"] = []
        self.draft("--id", lid, "--base", rev["revisionDigest"])
        self.assertIn("unsupported_clear", self.call("plan", "--id", lid, "--action", "save-draft", fail=True)["error"])

    def test_stale_base_and_read_only_status(self):
        rev = self.draft()
        lid = rev["localId"]
        self.brief["payload"]["name"] = "First edit"
        changed = self.draft("--id", lid, "--base", rev["revisionDigest"])
        repeated = self.draft("--id", lid, "--base", rev["revisionDigest"])
        self.assertEqual(changed["revision"], repeated["revision"])
        self.brief["payload"]["name"] = "Competing edit"
        (self.project / "brief.json").write_text(json.dumps(self.brief))
        self.call("draft", "--id", lid, "--brief", "brief.json", "--base", rev["revisionDigest"], fail=True)
        def paths():
            return sorted(p.relative_to(self.project) for p in self.project.rglob("*"))
        before = paths()
        self.call("status", "--id", lid)
        self.call("review", "--id", lid)
        self.assertEqual(before, paths())

    def test_ci_does_not_dispatch(self):
        lid = self.draft()["localId"]
        plan = self.authorize(lid, "save-draft")
        self.env["CI"] = "true"
        self.call("execute", "--plan", plan, fail=True)
        self.assertEqual(self.call("status", "--id", lid)["pending"], {})
        self.assertFalse((self.root / "writes").exists())
