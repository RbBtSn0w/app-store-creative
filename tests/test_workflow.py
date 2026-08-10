import importlib.util
import json
import struct
import tempfile
import unittest
from unittest import mock
import zlib
from pathlib import Path

MODULE = Path(__file__).parents[1] / "plugins/app-store-creative/scripts/creative_workflow.py"
SPEC = importlib.util.spec_from_file_location("creative_workflow", MODULE)
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
import sys
sys.modules[SPEC.name] = workflow
SPEC.loader.exec_module(workflow)

ADAPTER_SPEC = importlib.util.spec_from_file_location("recording_adapters", MODULE.parent / "recording_adapters.py")
adapters = importlib.util.module_from_spec(ADAPTER_SPEC); ADAPTER_SPEC.loader.exec_module(adapters)
PREVIEW_SPEC = importlib.util.spec_from_file_location("produce_app_preview", MODULE.parent / "produce_app_preview.py")
preview = importlib.util.module_from_spec(PREVIEW_SPEC); PREVIEW_SPEC.loader.exec_module(preview)
PUBLIC_SPEC = importlib.util.spec_from_file_location("app_store_creative", MODULE.parent / "app_store_creative.py")
public = importlib.util.module_from_spec(PUBLIC_SPEC); PUBLIC_SPEC.loader.exec_module(public)


def png(path: Path, width=10, height=20):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"\x00" + b"\x00\x00\x00" * width
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                     chunk(b"sRGB", b"\x00") + chunk(b"IDAT", zlib.compress(raw * height)) + chunk(b"IEND", b""))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = workflow.Store(self.root)
        workflow.command_init(type("A", (), {"root": self.root, "project": "Example"})())

    def tearDown(self): self.temp.cleanup()

    def plan(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"tasks": [{"kind": "screenshot", "locale": "en-US", "device": "iphone",
                                                     "output": "out/a.png", "dimensions": [10, 20]}]}))
        return workflow.command_plan(type("A", (), {"root": self.root, "manifest": manifest, "run_id": "run-a"})())["task_ids"][0]

    def claim_args(self, task_id, **extra):
        values = {"root": self.root, "run_id": "run-a", "task_id": task_id, "owner": "worker",
                  "ttl_seconds": 60, "reclaim_expired": False, **extra}
        values.setdefault("release_claim", False)
        return type("A", (), values)()

    def test_deterministic_plan_and_immutable_task(self):
        task_id = self.plan()
        first = self.store.task_path(task_id).read_bytes()
        self.assertEqual(self.plan(), task_id)
        self.assertEqual(self.store.task_path(task_id).read_bytes(), first)

    def test_claim_is_atomic_and_token_is_required(self):
        task_id = self.plan()
        args = self.claim_args(task_id)
        claim = workflow.command_claim(args)
        with self.assertRaisesRegex(workflow.WorkflowError, "already claimed"):
            workflow.command_claim(args)
        png(self.root / "out/a.png")
        with self.assertRaisesRegex(workflow.WorkflowError, "token mismatch"):
            workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": "wrong", "producer_receipt": self.root / "none"})())
        producer = self.root / "producer.json"; producer.write_text(json.dumps({"task_id": task_id, "tool": "test"}))
        receipt = workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": claim["token"], "producer_receipt": producer})())
        self.assertEqual(receipt["asset"]["width"], 10)
        self.assertEqual(receipt["producer_receipt_sha256"], workflow.file_digest(producer))
        self.assertEqual(workflow.load_json(self.store.state / "receipts" / f"{task_id}.json")["producer_receipt"], {"task_id": task_id, "tool": "test"})
        self.assertFalse((self.store.state / "claims" / f"{task_id}.json").exists())

    def test_png_dimensions_are_enforced(self):
        task_id = self.plan(); png(self.root / "out/a.png", 1, 2)
        with self.assertRaisesRegex(workflow.WorkflowError, "dimension mismatch"):
            workflow.command_verify(type("A", (), {"root": self.root, "task_id": task_id})())

    def test_upload_requires_both_immutable_approvals_and_is_dry_run(self):
        task_id = self.plan(); png(self.root / "out/a.png")
        claim = workflow.command_claim(self.claim_args(task_id))
        producer = self.root / "producer.json"; producer.write_text("{}")
        workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": claim["token"], "producer_receipt": producer})())
        base = {"root": self.root, "task_id": task_id, "approver": "reviewer"}
        workflow.command_approve(type("A", (), {**base, "stage": "design", "input_sha256": "manifest"})())
        plan = workflow.command_upload_plan(type("A", (), {"root": self.root, "task_id": task_id})())
        plan_file = self.root / "plan.json"; plan_file.write_text(json.dumps({"plans": [plan]})); plan_hash = workflow.file_digest(plan_file)
        workflow.command_approve(type("A", (), {**base, "stage": "upload", "approver": "uploader", "input_sha256": plan_hash})())
        result = workflow.command_upload(type("A", (), {"root": self.root, "plan_id": plan["plan_id"], "execute": False, "plan_sha256": plan_hash})())
        self.assertFalse(result["executed"])
        with self.assertRaisesRegex(workflow.WorkflowError, "no upload adapter"):
            workflow.command_upload(type("A", (), {"root": self.root, "plan_id": plan["plan_id"], "execute": True, "plan_sha256": plan_hash})())

    def test_expired_claim_is_scoped_and_reclaimable(self):
        task_id = self.plan()
        claim = workflow.command_claim(self.claim_args(task_id, ttl_seconds=1))
        path = self.store.state / "claims" / f"{task_id}.json"; body = workflow.load_json(path); body["expires_at"] = 0; workflow.atomic_write(path, body)
        status = workflow.command_status(type("A", (), {"root": self.root, "run_id": "run-a"})())
        self.assertEqual(status["tasks"][0]["state"], "expired")
        reclaimed = workflow.command_claim(self.claim_args(task_id, reclaim_expired=True))
        self.assertNotEqual(claim["token"], reclaimed["token"])
        released = workflow.command_claim(self.claim_args(task_id, release_claim=True))
        self.assertTrue(released["released"])

    def test_status_does_not_mix_runs(self):
        first = self.plan()
        manifest = self.root / "other.json"; manifest.write_text(json.dumps({"tasks": [{"kind": "screenshot", "locale": "fr-FR", "device": "iphone", "output": "out/b.png"}]}))
        other = workflow.command_plan(type("A", (), {"root": self.root, "manifest": manifest, "run_id": "run-b"})())["task_ids"][0]
        status = workflow.command_status(type("A", (), {"root": self.root, "run_id": "run-a"})())
        self.assertEqual([t["id"] for t in status["tasks"]], [first]); self.assertNotIn(other, [t["id"] for t in status["tasks"]])

    def test_promotion_copies_atomically_and_writes_release_manifest(self):
        task_id = self.plan(); destination = self.root / "out/a.png"; png(destination)
        claim = workflow.command_claim(self.claim_args(task_id)); producer = self.root / "producer.json"; producer.write_text("{}")
        workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": claim["token"], "producer_receipt": producer})())
        run = workflow.load_json(self.store.state / "runs/run-a.json")
        workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "design",
                                                  "approver": "reviewer", "input_sha256": run["manifest_sha256"]})())
        inputs = self.root / "inputs"; png(inputs / "out/a.png"); old_hash = workflow.file_digest(destination)
        manifest = workflow.promote_release(self.root, "run-a", inputs)
        self.assertEqual(manifest["assets"][0]["sha256"], old_hash)
        self.assertTrue((self.store.state / "releases/run-a.json").is_file())

    def test_audit_detects_event_tampering(self):
        self.plan()
        self.assertTrue(workflow.command_audit(type("A", (), {"root": self.root})())["ok"])
        event = sorted((self.store.state / "events").glob("*.json"))[0]
        body = json.loads(event.read_text()); body["kind"] = "tampered"; event.write_text(json.dumps(body))
        self.assertFalse(workflow.command_audit(type("A", (), {"root": self.root})())["ok"])

    def test_recording_adapters_are_strict_and_side_effect_free(self):
        self.assertEqual(adapters.ios_simulator_command("ABC-123", Path("preview.mov"))[:5],
                         ["xcrun", "simctl", "io", "ABC-123", "recordVideo"])
        with self.assertRaises(adapters.RecordingContractError):
            adapters.macos_screencapturekit_contract(bundle_id="com.example", output=Path("a.mov"), capture_scope="desktop")
        with self.assertRaises(adapters.RecordingContractError):
            adapters.macos_screencapturekit_contract(bundle_id="com.example", output=Path("a.mov"), include_cursor=True)

    def test_preview_dry_run_supports_silent_segments_and_timed_overlay(self):
        contract = {"width": 1080, "height": 1920, "fps": 30, "duration": 5,
                    "segments": [{"path": "silent.mov", "duration": 5, "has_audio": False}],
                    "overlays": [{"type": "text", "text": "Hello", "start": 1, "end": 3}]}
        command = preview.build_command(contract, Path("preview.mp4"))
        joined = " ".join(command)
        self.assertIn("anullsrc", joined); self.assertIn("drawtext", joined)
        self.assertIn("libx264", command); self.assertIn("aac", command)

    def test_preview_supports_image_overlay_end_card_and_rejects_duration_drift(self):
        contract = {"width": 1080, "height": 1920, "fps": 30, "duration": 6,
                    "segments": [{"path": "segment.mov", "duration": 5, "has_audio": False}],
                    "overlays": [{"type": "image", "path": "badge.png", "start": 1, "end": 3, "x": 10, "y": 20}],
                    "end_card": {"path": "end.png", "duration": 1}}
        command = preview.build_command(contract, Path("preview.mp4")); joined = " ".join(command)
        self.assertIn("badge.png", command); self.assertIn("end.png", command); self.assertIn("overlay=x=10:y=20", joined)
        contract["duration"] = 7
        with self.assertRaisesRegex(ValueError, "durations"):
            preview.build_command(contract, Path("preview.mp4"))

    def test_confined_rejects_symlink_escape(self):
        outside = Path(self.temp.name).parent / "outside-creative-test"; outside.mkdir(exist_ok=True)
        link = self.root / "escaped"; link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(workflow.WorkflowError, "escapes repository"):
            workflow.confined(self.root, link / "asset.png", "asset")

    def test_promotion_preserves_nested_paths_with_duplicate_basenames(self):
        manifest_path = self.root / "nested.json"
        manifest_path.write_text(json.dumps({"tasks": [
            {"kind": "screenshot", "locale": "en-US", "device": "a", "output": "release/a/icon.png", "dimensions": [10, 20]},
            {"kind": "screenshot", "locale": "en-US", "device": "b", "output": "release/b/icon.png", "dimensions": [10, 20]}]}))
        run = workflow.command_plan(type("A", (), {"root": self.root, "manifest": manifest_path, "run_id": "nested"})())
        inputs = self.root / "inputs"
        for index, task_id in enumerate(run["task_ids"]):
            task = workflow.load_json(self.store.task_path(task_id)); output = self.root / task["output"]
            png(output); output.write_bytes(output.read_bytes() + bytes([index]))
            claim = workflow.command_claim(type("A", (), {"root": self.root, "run_id": "nested", "task_id": task_id,
                                                           "owner": "worker", "ttl_seconds": 60, "reclaim_expired": False, "release_claim": False})())
            producer = self.root / f"producer-{index}.json"; producer.write_text("{}")
            workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": claim["token"], "producer_receipt": producer})())
            source = inputs / task["output"]; source.parent.mkdir(parents=True, exist_ok=True); source.write_bytes(output.read_bytes())
            png(output, 10, 20)  # Existing destination differs and must be replaced.
            workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "design", "approver": "reviewer",
                                                      "input_sha256": workflow.file_digest(manifest_path)})())
        promoted = workflow.promote_release(self.root, "nested", inputs)
        self.assertEqual(len(promoted["assets"]), 2)
        self.assertNotEqual(workflow.file_digest(self.root / "release/a/icon.png"), workflow.file_digest(self.root / "release/b/icon.png"))

    def test_promotion_restores_replaced_destination_on_failure(self):
        task_id = self.plan(); destination = (self.root / "out/a.png").resolve(); png(destination); destination.write_bytes(destination.read_bytes() + b"new")
        claim = workflow.command_claim(self.claim_args(task_id)); producer = self.root / "producer.json"; producer.write_text("{}")
        workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": claim["token"], "producer_receipt": producer})())
        inputs = self.root / "inputs"; source = inputs / "out/a.png"; source.parent.mkdir(parents=True); source.write_bytes(destination.read_bytes())
        png(destination); old_hash = workflow.file_digest(destination)
        run = workflow.load_json(self.store.state / "runs/run-a.json")
        workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "design", "approver": "reviewer",
                                                  "input_sha256": run["manifest_sha256"]})())
        original_replace = workflow.os.replace; failed = False
        def fail_once(src, dst):
            nonlocal failed
            if not failed and Path(dst) == destination and "backups" not in Path(src).parts:
                failed = True; raise OSError("injected promotion failure")
            return original_replace(src, dst)
        with mock.patch.object(workflow.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "injected"):
                workflow.promote_release(self.root, "run-a", inputs)
        self.assertEqual(workflow.file_digest(destination), old_hash)

    def test_approval_separation_and_immutable_reapproval_history(self):
        task_id = self.plan(); png(self.root / "out/a.png")
        claim = workflow.command_claim(self.claim_args(task_id)); producer = self.root / "producer.json"; producer.write_text("{}")
        workflow.command_complete(type("A", (), {"root": self.root, "task_id": task_id, "token": claim["token"], "producer_receipt": producer})())
        with self.assertRaisesRegex(workflow.WorkflowError, "self approval"):
            workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "design", "approver": "worker", "input_sha256": "one"})())
        first = workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "design", "approver": "designer", "input_sha256": "one"})())
        second = workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "design", "approver": "designer", "input_sha256": "two"})())
        directory = self.store.state / "approvals" / f"{task_id}-design"
        self.assertTrue((directory / f"{first['approval_sha256']}.json").exists())
        self.assertEqual(workflow.approval(self.store, task_id, "design")["approval_sha256"], second["approval_sha256"])
        with self.assertRaisesRegex(workflow.WorkflowError, "differ"):
            workflow.command_approve(type("A", (), {"root": self.root, "task_id": task_id, "stage": "upload", "approver": "designer", "input_sha256": "plan"})())

    def test_task_kind_is_bound_to_media_type(self):
        manifest = self.root / "preview.json"; manifest.write_text(json.dumps({"tasks": [{"kind": "app_preview", "locale": "en-US", "device": "iphone", "output": "out/preview.png"}]}))
        task_id = workflow.command_plan(type("A", (), {"root": self.root, "manifest": manifest, "run_id": "preview"})())["task_ids"][0]
        png(self.root / "out/preview.png")
        with self.assertRaisesRegex(workflow.WorkflowError, "app_preview"):
            workflow.command_verify(type("A", (), {"root": self.root, "task_id": task_id})())

    def test_public_audit_is_read_only_and_local_only(self):
        release = self.root / "release.json"; release.write_text(json.dumps({"tasks": []}))
        before = sorted((self.store.state / "events").glob("*.json"))
        result = public.run(type("A", (), {"command": "audit", "repo": self.root, "release": release,
                                             "app": "123", "version_id": "456"})())
        self.assertEqual(result["scope"], "local_integrity"); self.assertFalse(result["remote_verified"])
        self.assertEqual(before, sorted((self.store.state / "events").glob("*.json")))


if __name__ == "__main__": unittest.main()
