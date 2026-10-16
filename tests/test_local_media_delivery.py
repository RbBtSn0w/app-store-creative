"""Unit tests for TASK-201: Local Media Delivery & Decoupled Git Binding (Issue #45)."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
sys.path.insert(0, str(Path(__file__).parent))

import artifact_lifecycle as lifecycle
from archive_policy import resolve as resolve_archive_policy
from test_v2_workflow import create_mock_png


class LocalMediaDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {
            "project": {"id": "demo", "name": "Demo", "bundleId": "example.demo", "locales": ["en-US"]},
            "targets": ["mac_16_10"],
            "cards": [{"id": "hero", "screenshot": "source.png"}],
            "archivePolicy": {"schema_version": 1, "mediaMode": "local"},
            "artifactPolicy": {"schema_version": 1, "mediaBudgetBytes": 1073741824},
        }
        self.target = {
            "app_id": "123456",
            "bundle_id": "example.demo",
            "version_id": "version-resource",
            "platform": "MAC_OS",
        }

    def _setup_sealed_delivery(self):
        store = lifecycle.Lifecycle(self.root, self.config)
        run = store.start_run({"version": "1.5", "platform": "MAC_OS"})
        attempt = store.start_attempt(run["id"], "render", "agent")
        source = self.root / "source.png"
        create_mock_png(source, 2880, 1800)
        inp = store.register(attempt["id"], source, "source", logical_path="source.png")
        out = store.register(attempt["id"], source, "screenshot", inputs=[inp["id"]],
                              logical_path="en-US/mac_16_10/hero.png")
        store.finish_attempt(attempt["id"], "succeeded")
        candidate = store.select(run["id"], [out["id"]])
        validation = store.validate_candidate(candidate["id"])
        self.assertEqual(validation["status"], "PASS", validation.get("errors"))
        approval = store.approve_design(candidate["id"], validation["id"], "owner", "human:design")
        delivery = store.seal(candidate["id"], validation["id"], approval["id"])
        return store, delivery

    def test_archive_policy_local_mode_validation(self):
        valid = {"schema_version": 1, "mediaMode": "local"}
        self.assertEqual(resolve_archive_policy({"archivePolicy": valid}), valid)

        with self.assertRaisesRegex(ValueError, "archive policy"):
            resolve_archive_policy({"archivePolicy": {"schema_version": 1, "mediaMode": "local", "backend": "forbidden"}})

    def test_local_delivery_plan_without_git_repository(self):
        store, delivery = self._setup_sealed_delivery()
        self.assertEqual(delivery["archive_policy"]["mediaMode"], "local")

        # Plan publication without any git repo initialized or commit given
        plan = store.plan_publication(delivery["id"], remote_target=self.target, local_delivery=True)
        self.assertEqual(plan["delivery_id"], delivery["id"])
        self.assertEqual(plan["archive_commit"], "local")
        self.assertEqual(plan["manifest_sha256"], delivery["manifest_sha256"])
        self.assertEqual(plan["retrieval_proof"]["media_mode"], "local")
        self.assertTrue(plan["retrieval_proof"]["retrieval_verified"])

        # Check local delivery bundle in publications/<pub-id>/local_delivery/
        local_dir = store.paths.publications / plan["id"] / "local_delivery"
        self.assertTrue(local_dir.is_dir())
        manifest_file = local_dir / "manifest.json"
        self.assertTrue(manifest_file.is_file())
        receipt_file = local_dir / "receipt.json"
        self.assertTrue(receipt_file.is_file())

        receipt = json.loads(receipt_file.read_text())
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["publication_id"], plan["id"])
        self.assertEqual(receipt["delivery_id"], delivery["id"])
        self.assertEqual(receipt["manifest_sha256"], delivery["manifest_sha256"])
        self.assertEqual(receipt["media_mode"], "local")
        self.assertTrue(receipt["files_verified"])
        self.assertTrue(receipt["offline_validation"]["package_verified"])

        # Verify asset files are copied to local_delivery
        copied_asset = local_dir / "media/en-US/mac_16_10/hero.png"
        self.assertTrue(copied_asset.is_file())

        # Test upload approval and export with local_delivery_path
        approval = store.approve_upload(plan["id"], "owner", "human:upload")
        self.assertEqual(approval["stage"], "upload")
        self.assertEqual(approval["publication_id"], plan["id"])

        exported = store.export_publication(plan["id"], write=True)
        self.assertIn("local_delivery_path", exported)
        self.assertEqual(exported["local_delivery_path"], str(local_dir))
        self.assertTrue(Path(exported["handoff_path"]).is_file())

    def test_cli_publication_plan_local_delivery(self):
        import argparse
        from lifecycle_commands import add_commands, execute
        store, delivery = self._setup_sealed_delivery()
        target_path = self.root / "target.json"
        target_path.write_text(json.dumps(self.target))

        (self.root / "creative.config.json").write_text(json.dumps(self.config))
        parser = argparse.ArgumentParser()
        parser.add_argument("--repo", type=Path, default=self.root)
        parser.add_argument("--config", type=Path, default=None)
        add_commands(parser.add_subparsers(dest="command", required=True))

        args = parser.parse_args([
            "publication",
            "--repo", str(self.root),
            "plan",
            "--delivery-id", delivery["id"],
            "--target", str(target_path),
            "--local-delivery",
        ])
        result = execute(args)
        self.assertEqual(result["delivery_id"], delivery["id"])
        self.assertEqual(result["archive_commit"], "local")
        local_dir = store.paths.publications / result["id"] / "local_delivery"
        self.assertTrue((local_dir / "manifest.json").is_file())
        self.assertTrue((local_dir / "receipt.json").is_file())


if __name__ == "__main__":
    unittest.main()
