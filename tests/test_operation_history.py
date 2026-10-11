"""Durable production commits and incomplete writes remain distinguishable."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import test_artifact_lifecycle as fixtures


class OperationHistoryTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_successful_production_has_verifiable_commit_events(self):
        run = self.store.start_run({"version": "1.5"})
        attempt = self.store.start_attempt(run["id"], "capture", "agent-a")
        source = self.root / "take.bin"; source.write_bytes(b"product bytes")
        self.store.register(attempt["id"], source, "capture")
        self.store.finish_attempt(attempt["id"], "failed", "wrong locale")
        result = self.store.verify_history()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(len(result["events"]), 5)
        self.assertEqual({row["status"] for row in result["events"]}, {"COMMITTED"})
        self.assertEqual(result["untracked_records"], [])

    def test_record_tampering_is_not_committed_evidence(self):
        run = self.store.start_run({})
        path = self.store._path("runs", run["id"])
        path.write_text(json.dumps({**run, "target": {"version": "changed"}}))
        result = self.store.verify_history()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["events"][0]["status"], "CHANGED")

    def test_missing_event_does_not_hide_committed_record(self):
        run = self.store.start_run({})
        next((self.store.paths.workspace / "records/events").glob("*.json")).unlink()
        result = self.store.verify_history()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["untracked_records"], ["runs/" + run["id"] + ".json"])

    def test_record_write_failure_preserves_incomplete_intent(self):
        original = self.store._write_path
        def fail_record(path, data):
            if path.parent.name == "runs":
                raise OSError("record publication failed")
            return original(path, data)
        with mock.patch.object(self.store, "_write_path", side_effect=fail_record):
            with self.assertRaisesRegex(OSError, "publication failed"):
                self.store.start_run({})
        result = self.store.verify_history()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["events"][0]["status"], "INCOMPLETE")

    def test_event_write_failure_never_publishes_record(self):
        original = self.store._write_path
        def fail_event(path, data):
            if path.parent.name == "events":
                raise OSError("event publication failed")
            return original(path, data)
        with mock.patch.object(self.store, "_write_path", side_effect=fail_event):
            with self.assertRaisesRegex(OSError, "event publication failed"):
                self.store.start_run({})
        self.assertEqual(list((self.store.paths.workspace / "records/runs").glob("*.json")), [])

    def test_public_cli_verifies_history_without_modifying_it(self):
        (self.root / "creative.config.json").write_text(json.dumps(self.cfg))
        self.store.start_run({})
        before = {str(path): path.read_bytes() for path in self.store.paths.workspace.rglob("*") if path.is_file()}
        cli = Path(__file__).parents[1] / "plugins/app-store-creative/scripts/app_store_creative.py"
        result = subprocess.run([sys.executable, str(cli), "history", "verify", "--repo", str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "PASS")
        after = {str(path): path.read_bytes() for path in self.store.paths.workspace.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_event_identity_cannot_be_removed_from_commit_evidence(self):
        self.store.start_run({})
        path = next((self.store.paths.workspace / "records/events").glob("*.json"))
        event = json.loads(path.read_text()); event.pop("executor")
        path.write_text(json.dumps(event))
        with self.assertRaisesRegex(ValueError, "event|executor"):
            self.store.verify_history()

    def test_two_events_cannot_claim_the_same_record_commit(self):
        self.store.start_run({})
        path = next((self.store.paths.workspace / "records/events").glob("*.json"))
        event = json.loads(path.read_text()); event["id"] = "duplicate-event"
        self.store._write_path(self.store._path("events", event["id"]), event)
        result = self.store.verify_history()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["duplicate_references"]), 1)

    def test_studio_history_matches_core_without_writes(self):
        import export_engine
        import test_studio_release
        (self.root / "creative.config.json").write_text(json.dumps(self.cfg))
        self.store.start_run({})
        before = {str(path): path.read_bytes() for path in self.store.paths.workspace.rglob("*") if path.is_file()}
        with export_engine.LocalServerContext(self.root, self.root / "creative.config.json") as ctx:
            result, _ = test_studio_release.StudioReleaseTests.request(self, ctx, "/api/history")
            self.assertEqual(result, self.store.verify_history())
        after = {str(path): path.read_bytes() for path in self.store.paths.workspace.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_studio_history_rejects_arbitrary_workspace_query(self):
        import export_engine
        import test_studio_release
        import urllib.error
        (self.root / "creative.config.json").write_text(json.dumps(self.cfg))
        with export_engine.LocalServerContext(self.root, self.root / "creative.config.json") as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                test_studio_release.StudioReleaseTests.request(self, ctx, "/api/history?workspace=/tmp/elsewhere")
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()

    def test_recovery_distinguishes_uncommitted_outcome_intent(self):
        from datetime import datetime, timedelta, timezone
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run["id"], "capture", "first-agent")
        original = self.store._write_path
        def fail_outcome(path, data):
            if path.name == "outcome.json":
                raise OSError("outcome publication failed")
            return original(path, data)
        with mock.patch.object(self.store, "_write_path", side_effect=fail_outcome):
            with self.assertRaises(OSError):
                self.store.finish_attempt(attempt["id"], "succeeded")
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        with mock.patch("lease_lifecycle.utcnow", return_value=future):
            self.store.recover_attempt(attempt["id"], "replacement-agent", "producer lost")
        result = self.store.verify_history()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual([row["status"] for row in result["events"]].count("NOT_COMMITTED"), 1)

    def test_lease_is_rechecked_after_event_persistence(self):
        import operation_history
        import lease_lifecycle
        from datetime import timedelta
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run["id"], "capture", "agent")
        source = self.root / "take.bin"; source.write_bytes(b"product bytes")
        expired = [False]
        original_time = lease_lifecycle.utcnow
        original_commit = operation_history.before_commit
        def commit(*args):
            original_commit(*args)
            expired[0] = True
        def current_time():
            return original_time() + (timedelta(hours=2) if expired[0] else timedelta())
        with mock.patch("operation_history.before_commit", side_effect=commit), mock.patch("lease_lifecycle.utcnow", side_effect=current_time):
            with self.assertRaisesRegex(ValueError, "expired"):
                self.store.register(attempt["id"], source, "capture")
        self.assertEqual(list((self.store.paths.workspace / "records/artifacts").glob("*.json")), [])

    def test_malformed_record_commit_binding_reports_changed(self):
        run = self.store.start_run({})
        path = self.store._path("runs", run["id"])
        for binding in (None, True, {}, []):
            with self.subTest(binding=binding):
                path.write_text(json.dumps({**run, "_commit_event_id": binding}))
                result = self.store.verify_history()
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["events"][0]["status"], "CHANGED")

    def test_business_reads_refuse_missing_commit_binding(self):
        run = self.store.start_run({})
        path = self.store._path("runs", run["id"])
        legacy = dict(run); legacy.pop("_commit_event_id")
        path.write_text(json.dumps(legacy))
        with self.assertRaisesRegex(ValueError, "commit event binding"):
            self.store.status(run["id"])
