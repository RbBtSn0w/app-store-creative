"""Retention plans distinguish redundant registered objects from retained evidence."""
import json
import unittest
from pathlib import Path
import test_forward_source_inventory as fixtures


class RelocationRetentionPlanTests(unittest.TestCase):
    setUp = fixtures.ForwardSourceInventoryTests.setUp
    source = fixtures.ForwardSourceInventoryTests.source
    targets = fixtures.ForwardSourceInventoryTests.targets
    prepared = fixtures.ForwardSourceInventoryTests.prepared
    moved = fixtures.ForwardSourceInventoryTests.moved
    def test_plan_pins_recoverable_object_and_preserves_evidence(self):
        active, move, artifact = self.moved()
        before = self.store.object_path(artifact['sha256']).read_bytes()
        plan = active.plan_relocation_retention(retention_days=0)
        entries = [item for item in plan['files'] if item['decision'] == 'eligible']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['decision'], 'eligible')
        self.assertEqual(entries[0]['recovery']['path'], str(active.object_path(artifact['sha256'])))
        self.assertEqual(self.store.object_path(artifact['sha256']).read_bytes(), before)
        self.assertTrue(any(item['reason'] == 'retained-evidence' for item in plan['files']))
        self.assertFalse(plan['cleanup_executed'])
        self.assertEqual(active._read('maintenance', plan['id']), plan)

    def test_unexpired_copy_is_protected(self):
        active, move, artifact = self.moved()
        plan = active.plan_relocation_retention(retention_days=30)
        self.assertFalse(any(item['decision'] == 'eligible' for item in plan['files']))
        self.assertTrue(any(item['reason'] == 'retention-not-expired' for item in plan['files']))

    def test_missing_recovery_object_is_protected(self):
        active, move, artifact = self.moved()
        active.object_path(artifact['sha256']).unlink()
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertTrue(any(item['reason'] == 'no-verified-independent-copy' for item in plan['files']))
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_changed_copy_is_excluded_without_touching_notes(self):
        active, move, artifact = self.moved()
        note = self.store.paths.workspace / 'owner-note'; note.write_text('Keep')
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertTrue(any(item['status'] == 'CHANGED' for item in plan['excluded_roots']))
        self.assertEqual(note.read_text(), 'Keep')

    def test_policy_requires_explicit_nonnegative_integer(self):
        active, move, artifact = self.moved()
        for value in (True, -1, 1.5):
            with self.assertRaises(ValueError):
                active.plan_relocation_retention(retention_days=value)

    def test_configured_absolute_source_file_stays_protected(self):
        active, move, artifact = self.moved()
        config = json.loads(active.config_path.read_text())
        config['sourcePath'] = str(self.store.object_path(artifact['sha256']))
        active.config_path.write_text(json.dumps(config))
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertTrue(any(item['reason'] == 'configured-source-path' for item in plan['files']))
        self.assertFalse(any(item['decision'] == 'eligible' for item in plan['files']))

    def test_corrupt_recovery_is_not_a_recoverable_copy(self):
        active, move, artifact = self.moved()
        active.object_path(artifact['sha256']).write_bytes(b'corrupt')
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertFalse(any(item['decision'] == 'eligible' for item in plan['files']))

    def test_hardlink_is_not_an_independent_recovery_copy(self):
        import os
        active, move, artifact = self.moved()
        recovery = active.object_path(artifact['sha256'])
        recovery.unlink(); os.link(self.store.object_path(artifact['sha256']), recovery)
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertFalse(any(item['decision'] == 'eligible' for item in plan['files']))

    def test_reverse_backup_can_plan_registered_object_only(self):
        from artifact_lifecycle import Lifecycle
        active, move, artifact = self.moved()
        reverse = active.plan_reverse_relocation(move['id'])
        active.prepare_reverse_relocation(reverse['id'], 'owner', 'Return')
        active.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(active.config_path.read_text()))
        plan = returned.plan_relocation_retention(retention_days=0)
        eligible = [item for item in plan['files'] if item['decision'] == 'eligible']
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]['relocation_id'], reverse['id'])
        self.assertEqual(eligible[0]['recovery']['path'], str(returned.object_path(artifact['sha256'])))

    def test_pending_migration_protects_existing_copies(self):
        active, move, artifact = self.moved()
        pending = active.plan_relocation({'workspaceRoot': 'third work', 'objectRoot': 'third objects',
            'releaseRoot': 'third deliveries', 'publicationRoot': 'third publications'})
        active.prepare_relocation(pending['id'], 'owner', 'Prepare another move')
        plan = active.plan_relocation_retention(retention_days=0)
        self.assertFalse(any(item['decision'] == 'eligible' for item in plan['files']))
        self.assertTrue(any(item['reason'] == 'pending-operation-or-unverified-evidence' for item in plan['files']))

    def test_public_cli_requires_explicit_policy(self):
        import argparse
        from lifecycle_commands import add_commands
        parser = argparse.ArgumentParser()
        add_commands(parser.add_subparsers(dest='command', required=True))
        args = parser.parse_args(['cleanup', 'plan-relocation-retention', '--retention-days', '12'])
        self.assertEqual(args.retention_days, 12)
