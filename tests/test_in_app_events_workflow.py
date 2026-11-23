import copy
import fcntl
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

RUNTIME = Path(__file__).resolve().parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime"
sys.path.insert(0, str(RUNTIME / "scripts"))
import event_assessment
import event_handoff
import event_plan as rules


def png(path, w, h):
    def chunk(tag, value):
        return struct.pack(">I", len(value)) + tag + value + struct.pack(">I", zlib.crc32(tag + value))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes((w + 1) * h)))
        + chunk(b"IEND", b"")
    )


class EventWorkflow(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve() / "project"
        self.inputs = self.root / "events"
        shutil.copytree(RUNTIME / "assets/templates/events", self.inputs)
        self.brief = rules.load(self.inputs / "walking-week.json")
        self.brief["appId"] = "123456789"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.start = self.now + timedelta(days=5)
        self.schedule = self.window(self.start, timedelta(days=7))
        self.brief["schedule"] = self.schedule
        self.write("brief", self.brief)
        self.inv = dict(
            schemaVersion=1,
            appId=self.brief["appId"],
            observedAt=self.now.isoformat(),
            complete=True,
            territories=["USA"],
            events=[],
            hasApprovedVersion=True,
        )
        self.routes = {k: self.brief[k] for k in ("bundleId", "buildRef", "eventKey", "deepLink")}
        self.routes.update(schemaVersion=1, checks=[])
        for phase in ("preheat", "cold", "warm", "onboarding", "expired"):
            self.routes["checks"].append(
                dict(
                    scenario=phase,
                    territory="USA",
                    eventKey="walking-week",
                    passed=True,
                    actionAvailable=True,
                    observedAt=self.now.isoformat(),
                    actualDestination=self.brief["destinations"].get(phase, "walking-week.challenge"),
                    evidence=self.brief["claims"][0],
                )
            )
        self.row = {
            k: self.brief[k]
            for k in (
                "referenceName",
                "schedule",
                "territories",
                "deepLink",
                "badge",
                "purpose",
                "priority",
                "purchaseRequirement",
                "primaryLocale",
            )
        }
        self.row.update(state="DRAFT", eventId="123", localizations={})
        self.snap = dict(
            schemaVersion=1,
            observedAt=self.now.isoformat(),
            appId=self.brief["appId"],
            eventKey="walking-week",
            complete=True,
            matches=[self.row],
        )

    def window(self, start, duration):
        return dict(
            publishAt=(start - timedelta(days=1)).isoformat(),
            startAt=start.isoformat(),
            endAt=(start + duration).isoformat(),
        )

    def write(self, name, value):
        (self.root / (name + ".json")).write_text(json.dumps(value))

    def cli(self, *args, code=0):
        cmd = [sys.executable, str(RUNTIME / "scripts/app_store_creative.py"), "events", *args]
        proc = subprocess.run(cmd, cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def run_event(self, action, *args, code=0):
        return self.cli("--repo", str(self.root), action, "--event", "walking-week", *args, code=code)

    def prepare(self):
        png(self.inputs / "card.png", 1920, 1080)
        png(self.inputs / "details.png", 1080, 1920)
        self.write("inv", self.inv)
        self.write("routes", self.routes)
        self.cli("plan", "--repo", str(self.root), "--brief", "brief.json")
        return self.run_event("validate", "--inventory", "inv.json", "--routes", "routes.json")

    def report(self, source="product", n=20, d=40):
        return dict(
            schemaVersion=1,
            source=source,
            appId=self.brief["appId"],
            eventKey="walking-week",
            eventId="123",
            window="event_start_to_end",
            territories=["USA"],
            **{"from": self.schedule["startAt"], "to": self.schedule["endAt"]},
            availability="available",
            metrics={"uniqueCompleters": n, "uniqueStarters": d},
            cohort="all_event_entrants",
            evidence=self.brief["claims"][0],
        )

    def test_cli_complete_replay(self):
        ready = self.prepare()
        self.assertEqual(ready["status"], "ready")
        pack = self.run_event("handoff", "--validation", ready["artifacts"]["validation"])
        self.assertEqual(self.run_event("handoff")["recordSha256"], pack["recordSha256"])
        self.row["state"] = "PUBLISHED"
        self.snap["handoffSha256"] = pack["recordSha256"]
        self.snap["evidence"] = self.brief["claims"][0]
        self.write("snapshot", self.snap)
        self.assertEqual(self.run_event("observe", "--snapshot", "snapshot.json")["status"], "published")
        self.write("report", self.report())
        measured = self.run_event("assess", "--product", "report.json")
        self.assertEqual(measured["status"], "threshold-met")
        self.assertIsNone(measured["store"])
        self.assertEqual(self.run_event("assess")["status"], "insufficient-data")
        self.assertTrue((self.root / measured["artifacts"]["assessment"]).is_file())

    def test_decisions_and_identity(self):
        result = self.cli("plan", "--repo", str(self.root), "--brief", "events/maintenance.json")
        self.assertEqual(result["status"], "skip")
        self.brief.pop("buildRef")
        self.assertEqual(rules.plan(self.root, self.brief)[0], "defer")
        self.brief["schemaVersion"] = True
        with self.assertRaises(ValueError):
            rules.plan(self.root, self.brief)

    def test_path_and_evidence_scope(self):
        (self.root / "escape").symlink_to(self.root.parent)
        with self.assertRaises(ValueError):
            rules.local(self.root, "escape/outside")
        self.brief["claims"][0]["sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "digest"):
            rules.plan(self.root, self.brief)
        self.brief["eventKey"] = "../bad"
        with self.assertRaises(ValueError):
            rules.plan(self.root, self.brief)

    def test_text_and_locales(self):
        row = self.brief["localizations"]["en-US"]
        for name, size in [("name", 30), ("shortDescription", 50), ("longDescription", 120)]:
            row[name] = "e\u0301" * size
            rules.fields(self.brief)
            row[name] += "x"
            with self.assertRaisesRegex(ValueError, name):
                rules.fields(self.brief)
            row[name] = "ok"
        self.brief["primaryLocale"] = "fr"
        with self.assertRaisesRegex(ValueError, "primary"):
            rules.fields(self.brief)

    def test_schedule_boundaries(self):
        for delta, ok in [
            (timedelta(minutes=15), True),
            (timedelta(seconds=899), False),
            (timedelta(days=31), True),
            (timedelta(days=31, seconds=1), False),
        ]:
            sched = self.window(self.start, delta)
            if ok:
                rules.windows(sched, ["USA"])
            else:
                with self.assertRaises(ValueError):
                    rules.windows(sched, ["USA"])
        self.schedule["publishAt"] = (self.start - timedelta(days=14)).isoformat()
        rules.windows(self.schedule, ["USA"])
        self.schedule["publishAt"] = (self.start - timedelta(days=14, seconds=1)).isoformat()
        with self.assertRaises(ValueError):
            rules.windows(self.schedule, ["USA"])

    def test_region_span_and_ambiguous_time(self):
        self.schedule["overrides"] = {"CAN": self.window(self.start + timedelta(hours=48), timedelta(days=1))}
        rules.windows(self.schedule, ["USA", "CAN"])
        self.schedule["overrides"]["CAN"] = self.window(
            self.start + timedelta(hours=48, seconds=1), timedelta(days=1)
        )
        with self.assertRaises(ValueError):
            rules.windows(self.schedule, ["USA", "CAN"])
        with self.assertRaises(ValueError):
            rules.timestamp("2026-11-01T01:30:00")

    def inventory_rows(self, count, state, window):
        return [
            dict(
                eventId=str(i), referenceName=f"event {i}", state=state, territories=["USA"], schedule=window
            )
            for i in range(count)
        ]

    def check_calendar(self, bound=None):
        return rules.calendar(self.brief, self.inv, self.now, bound)

    def test_distinct_capacity_limits(self):
        later = self.window(self.start + timedelta(days=30), timedelta(hours=3))
        self.inv["events"] = self.inventory_rows(49, "DRAFT", later)
        self.check_calendar()
        self.inv["events"] = self.inventory_rows(50, "DRAFT", later)
        with self.assertRaisesRegex(ValueError, "Draft capacity"):
            self.check_calendar()
        self.check_calendar("1")
        self.inv["events"] = self.inventory_rows(14, "PUBLISHED", later)
        self.assertTrue(self.check_calendar())
        self.inv["events"] = self.inventory_rows(15, "PUBLISHED", later)
        self.assertFalse(self.check_calendar())

    def test_preheat_overlap_half_open_and_duplicate_ids(self):
        end = rules.timestamp(self.schedule["publishAt"])
        early = self.window(end - timedelta(days=1), timedelta(days=1))
        self.inv["events"] = self.inventory_rows(10, "SET_TO_PUBLISH", early)
        self.inv["events"].append(self.inv["events"][0])
        self.check_calendar()
        early["endAt"] = (end + timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "display conflict"):
            self.check_calendar()
        self.inv["events"] = self.inventory_rows(10, "DRAFT", self.schedule)
        with self.assertRaisesRegex(ValueError, "activity conflict"):
            self.check_calendar()

    def test_unknown_or_stale_inventory(self):
        for change in [
            dict(complete=False),
            dict(observedAt=(self.now - timedelta(days=2)).isoformat()),
            dict(territories=["CAN"]),
            dict(appId="other"),
        ]:
            with self.assertRaises(ValueError):
                rules.calendar(self.brief, self.inv | change, self.now, None)

    def test_media_rejects_wrong_bytes_and_shape(self):
        path = self.inputs / "card.png"
        png(path, 1921, 1080)
        with self.assertRaisesRegex(ValueError, "dimensions"):
            rules.media(self.root, path, "card")
        png(path, 1920, 1080)
        path.write_bytes(path.read_bytes()[:-5])
        with self.assertRaises((ValueError, subprocess.SubprocessError)):
            rules.media(self.root, path, "card")
        with self.assertRaisesRegex(ValueError, "Static"):
            rules.media(self.root, "video.mp4", "details")

    def test_changed_asset_invalidates_handoff(self):
        self.prepare()
        png(self.inputs / "details.png", 1080, 1921)
        self.assertEqual(self.run_event("handoff", code=3)["status"], "blocked")

    def test_unknown_evidence_is_actionable(self):
        self.cli("plan", "--repo", str(self.root), "--brief", "brief.json")
        result = self.run_event("validate", code=3)
        self.assertEqual(
            {f["field"] for f in result["findings"] if f["code"] == "unknown"}, {"inventory", "routes"}
        )

    def test_route_scenarios(self):
        rules.routes(self.root, self.brief, self.routes)
        for field, value in [("actualDestination", "home"), ("passed", False), ("eventKey", "other")]:
            report = copy.deepcopy(self.routes)
            report["checks"][1][field] = value
            with self.assertRaises(ValueError):
                rules.routes(self.root, self.brief, report)
        for report in [
            self.routes | {"buildRef": "old"},
            self.routes | {"checks": self.routes["checks"][1:]},
        ]:
            with self.assertRaises(ValueError):
                rules.routes(self.root, self.brief, report)
        self.brief["additionalRouteScenarios"] = ["login"]
        with self.assertRaisesRegex(ValueError, "login"):
            rules.routes(self.root, self.brief, self.routes)

    def package(self):
        assets = {
            loc: {slot: {"path": row[slot], "sha256": "a" * 64} for slot in ["card", "details"]}
            for loc, row in self.brief["localizations"].items()
        }
        return event_handoff.handoff(self.brief, assets, self.inv, None) | {"approvalAvailable": True}

    def observe(self):
        return event_handoff.reconcile(self.package(), self.snap, {})

    def fill_remote(self):
        for loc, row in self.brief["localizations"].items():
            self.row["localizations"][loc] = dict(
                localizationId=loc,
                text={k: row[k] for k in ("name", "shortDescription", "longDescription")},
                assets={s: dict(assetId=s, sha256="a" * 64, state="COMPLETE") for s in ("card", "details")},
            )

    def test_paid_manual_and_version_route(self):
        self.brief["purchaseRequirement"] = "IN_APP_PURCHASE"
        self.inv["hasApprovedVersion"] = False
        package = self.package()
        self.assertIsNone(package["configureArgv"])
        self.assertEqual(package["submissionMode"], "with-version")
        self.fill_remote()
        self.row["purchaseRequirement"] = "IN_APP_PURCHASE"
        self.assertEqual(self.observe()["status"], "identify-version-submission")

    def test_creation_recovery_and_conflicts(self):
        for matches in [[], [self.row, self.row]]:
            self.snap["matches"] = matches
            self.assertEqual(self.observe()["actions"], [])
        self.snap["matches"] = [self.row]
        self.row["schedule"] = {}
        self.assertEqual(self.observe()["status"], "remote-conflict")
        self.row["schedule"] = self.schedule
        with self.assertRaisesRegex(ValueError, "identity"):
            event_handoff.reconcile(self.package(), self.snap, {"eventId": "another"})

    def test_only_missing_assets_and_submission_items(self):
        self.fill_remote()
        assets = self.row["localizations"]["zh-Hans"]["assets"]
        assets["card"]["state"] = "PROCESSING"
        self.assertEqual(self.observe()["status"], "await-delivery")
        assets["card"]["state"] = "FAILED"
        self.assertEqual(self.observe()["status"], "verify-asset")
        del assets["card"]
        actions = self.observe()["actions"]
        self.assertEqual([(a["action"], a["localizationId"]) for a in actions], [("upload", "zh-Hans")])
        self.fill_remote()
        self.row["submission"] = dict(
            appId=self.brief["appId"],
            platform="IOS",
            submissionId="88",
            state="READY_FOR_REVIEW",
            items=[dict(type="appEvents", id="other")],
        )
        self.assertEqual(self.observe()["status"], "review-submission-scope")
        self.row["submission"]["items"][0]["id"] = "123"
        self.assertEqual(self.observe()["actions"], [{"action": "submit-existing"}])

    def test_observed_states_and_read_failures(self):
        for state, expected in [
            ("REJECTED", "revise"),
            ("SET_TO_PUBLISH", "set-to-publish"),
            ("IN_REVIEW", "in-review"),
            ("PUBLISHED", "published"),
            ("PAST", "past"),
            ("NEW", "needs-review"),
        ]:
            self.row["state"] = state
            self.assertEqual(self.observe()["status"], expected)
        for status, expected in [
            ("forbidden", "check-access"),
            ("rate-limited", "retry-read"),
            ("write-unknown", "reconcile-before-write"),
        ]:
            self.snap["readStatus"] = status
            self.assertEqual(self.observe()["status"], expected)

    def test_assessment_boundaries(self):
        for n, d, status in [
            (39, 39, "insufficient-data"),
            (20, 40, "threshold-met"),
            (19, 40, "below-threshold"),
            (0, 0, "insufficient-data"),
        ]:
            result = event_assessment.assess(self.brief, {"eventId": "123"}, None, self.report(n=n, d=d))
            self.assertEqual(result["status"], status)
        suppressed = self.report("store") | {"availability": "suppressed", "metrics": {}}
        result = event_assessment.assess(self.brief, {"eventId": "123"}, suppressed, None)
        self.assertEqual(result["store"]["availability"], "suppressed")
        for changes in [
            dict(cohort="other"),
            dict(eventId="other"),
            dict(window="other"),
            dict(metrics={"uniqueStarters": False}),
            dict(metrics={"uniqueStarters": 1, "uniqueCompleters": 2}),
        ]:
            with self.assertRaises(ValueError):
                event_assessment.assess(self.brief, {"eventId": "123"}, None, self.report() | changes)

    def test_lock_contention_and_replay_after_exit(self):
        self.cli("plan", "--repo", str(self.root), "--brief", "brief.json")
        lockfile = self.root / ".creative/events/walking-week/event.lock"
        with lockfile.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_event("validate", code=3)
            self.assertIn("Concurrent", result["findings"][0]["actual"])
        current = self.cli("plan", "--repo", str(self.root), "--brief", "brief.json")
        self.assertEqual(current["status"], "propose")

    def test_stale_observation_does_not_replace_bound_event(self):
        self.prepare()
        package = self.run_event("handoff")
        self.snap.update(handoffSha256=package["recordSha256"], evidence=self.brief["claims"][0])
        self.write("snapshot", self.snap)
        first = self.run_event("observe", "--snapshot", "snapshot.json")
        self.snap["observedAt"] = (self.now - timedelta(minutes=1)).isoformat()
        self.write("snapshot", self.snap)
        self.run_event("observe", "--snapshot", "snapshot.json", code=3)
        latest = rules.load(self.root / ".creative/events/walking-week/observation.json")
        self.assertEqual(latest["snapshot"], first["snapshot"])

    def test_first_version_and_resume_partial_submission(self):
        self.fill_remote()
        self.inv["hasApprovedVersion"] = False
        self.brief["versionId"] = "version-42"
        self.assertEqual(self.observe()["status"], "locate-version-draft")
        self.row["submission"] = dict(
            submissionId="review",
            appId=self.brief["appId"],
            platform="IOS",
            state="READY_FOR_REVIEW",
            items=[{"type": "appStoreVersions", "id": "version-42"}],
        )
        self.assertEqual(self.observe()["actions"], [{"action": "add-event-to-existing"}])
        self.row["submission"]["items"][0]["id"] = "another-version"
        self.assertEqual(self.observe()["status"], "review-submission-scope")

    def test_expected_plan_rejects_stale_editor(self):
        args = ("plan", "--repo", str(self.root), "--brief", "brief.json")
        old = self.cli(*args)["recordSha256"]
        self.brief["audience"] = "New walkers"
        self.write("brief", self.brief)
        self.assertNotEqual(self.cli(*args, "--expected-plan", old)["recordSha256"], old)
        self.assertEqual(self.cli(*args, "--expected-plan", old, code=3)["status"], "blocked")

    def test_jpeg_and_missing_primary_image(self):
        source = self.inputs / "details.png"
        jpeg = self.inputs / "details.jpeg"
        png(source, 1080, 1920)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(source), "-frames:v", "1", str(jpeg)], check=True
        )
        self.assertEqual(rules.media(self.root, jpeg, "details")["height"], 1920)
        with self.assertRaises(FileNotFoundError):
            rules.media(self.root, self.inputs / "absent.jpg", "details")

    def test_interrupted_publisher_replays_only_remaining_work(self):
        # Replay the executor losing receipts after a create and after the first upload.
        self.snap["readStatus"] = "write-unknown"
        self.assertEqual(self.observe()["actions"], [])
        self.snap.pop("readStatus")
        self.assertEqual(self.observe()["eventId"], "123")
        self.fill_remote()
        for loc in self.row["localizations"].values():
            loc["assets"] = {}
        uploaded = []
        for _ in range(4):
            action = self.observe()["actions"][0]
            slot = "card" if action["assetType"] == "EVENT_CARD" else "details"
            locale = action["localizationId"]
            self.row["localizations"][locale]["assets"][slot] = dict(
                assetId=slot, state="COMPLETE", sha256=action["sha256"]
            )
            uploaded.append((locale, slot))
            self.assertNotIn(action, self.observe()["actions"])
        self.assertEqual(len(set(uploaded)), 4)
        self.assertEqual(self.observe()["status"], "ready-for-submission")

    def test_identical_and_revised_assessment(self):
        self.prepare()
        self.snap.update(
            handoffSha256=self.run_event("handoff")["recordSha256"], evidence=self.brief["claims"][0]
        )
        self.row["state"] = "PAST"
        self.write("snapshot", self.snap)
        self.run_event("observe", "--snapshot", "snapshot.json")
        self.write("product", self.report())
        old = self.run_event("assess", "--product", "product.json")
        self.assertEqual(
            old["recordSha256"], self.run_event("assess", "--product", "product.json")["recordSha256"]
        )
        self.write("product", self.report(n=19))
        new = self.run_event("assess", "--product", "product.json")
        self.assertNotEqual(old["recordSha256"], new["recordSha256"])
        self.assertTrue((self.root / old["artifacts"]["assessment"]).exists())
