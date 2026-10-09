"""Preparation staging is inventoried by pinned roots and planned bytes."""
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import test_relocation_switch as fixtures


class RelocationStagingInventoryTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def report(self, plan):
        return [item for item in self.store.inventory()['relocation_backups']['staging']
                if item['relocation_id'] == plan['id']]

    def test_prepared_roots_are_complete_and_inventory_is_read_only(self):
        artifact, plan = self.prepared()
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        roots = self.report(plan)
        self.assertTrue(roots)
        self.assertTrue(all(item['phase'] == 'PREPARED' and item['status'] == 'VERIFIED' for item in roots))
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_failed_copy_is_partial_and_preserves_unknown_file(self):
        self.source(); self.store.config_path.write_text(json.dumps(self.cfg))
        plan = self.store.plan_relocation(self.targets())
        with patch('relocation_lifecycle.shutil.copyfileobj', side_effect=OSError('Copy interrupted')):
            with self.assertRaisesRegex(OSError, 'Copy interrupted'):
                self.store.prepare_relocation(plan['id'], 'owner', 'Prepare')
        intent = self.store._read('relocations', plan['id'], 'prepare-intent')
        root = Path(next(iter(intent['staging'].values())))
        unknown = root / 'owner-notes'; unknown.write_text('Keep')
        rows = self.report(plan)
        self.assertTrue(all(item['phase'] == 'PREPARATION_FAILED' for item in rows))
        item = next(item for item in rows if item['path'] == str(root))
        self.assertEqual(item['status'], 'CHANGED'); self.assertIn('owner-notes', item['extra_files'])
        self.assertTrue(any(item['missing_files'] for item in rows)); self.assertTrue(unknown.exists())

    def test_same_bytes_root_replacement_is_conflict(self):
        artifact, plan = self.prepared()
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        root = Path(next(iter(prepared['staging'].values())))
        old = root.with_name(root.name + '-old'); root.rename(old); shutil.copytree(old, root)
        item = next(item for item in self.report(plan) if item['path'] == str(root))
        self.assertEqual(item['status'], 'IDENTITY_CONFLICT'); self.assertIsNone(item['observed_logical_bytes'])

    def test_cancelled_partial_reports_retained_unknown_file(self):
        artifact, plan = self.prepared()
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        root = Path(next(iter(prepared['staging'].values())))
        unknown = root / 'owner-notes'; unknown.write_text('Keep')
        self.store.cancel_relocation(plan['id'], 'owner', 'Stop')
        item = next(item for item in self.report(plan) if item['path'] == str(root))
        self.assertEqual(item['phase'], 'CANCELLED_PARTIAL')
        self.assertIn('owner-notes', item['extra_files']); self.assertTrue(unknown.exists())

    def test_modified_marker_does_not_authorize_scanning(self):
        artifact, plan = self.prepared()
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        root = Path(next(iter(prepared['staging'].values())))
        (root / '.relocation-owner.json').write_text('{}')
        item = next(item for item in self.report(plan) if item['path'] == str(root))
        self.assertEqual(item['status'], 'UNVERIFIED_OWNERSHIP'); self.assertIsNone(item['observed_logical_bytes'])

    def test_same_bytes_root_replacement_refuses_switch_before_fencing(self):
        artifact, plan = self.prepared()
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        root = Path(next(iter(prepared['staging'].values())))
        old = root.with_name(root.name + '-old'); root.rename(old); shutil.copytree(old, root)
        before = self.store.config_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'staging directory identity'):
            self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.store.start_run({})

    def test_published_unactivated_root_is_reported_at_actual_location(self):
        artifact, plan = self.prepared()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Config sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Config sync interrupted'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        row = next(row for row in self.report(plan) if row['group'] == 'objects')
        self.assertEqual(row['path'], plan['to']['objects'])
        self.assertEqual(row['kind'], 'pending-target')
        self.assertEqual(row['phase'], 'SWITCH_INTERRUPTED')
        self.assertEqual(row['status'], 'VERIFIED')
        self.assertGreater(row['observed_logical_bytes'], 0)

    def test_reverse_exchange_reports_pending_target_and_retained_old_copy(self):
        import test_reverse_relocation_switch as reverse_fixtures
        fixture = reverse_fixtures.ReverseRelocationSwitchTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        artifact, forward, moved, reverse, run = fixture.reverse()
        import delivery_lifecycle
        original = delivery_lifecycle.apply_directory_change
        def interrupt(change):
            original(change)
            raise OSError('After exchange')
        with patch('delivery_lifecycle.apply_directory_change', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'After exchange'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        rows = [row for row in moved.inventory()['relocation_backups']['staging'] if row['relocation_id'] == reverse['id']]
        self.assertTrue(any(row['kind'] == 'pending-backup' and row['status'] == 'VERIFIED' for row in rows))
        self.assertTrue(any(row['kind'] == 'pending-target' for row in rows))
        self.assertTrue(all(row['phase'] == 'SWITCH_INTERRUPTED' for row in rows))

    def test_replaced_published_root_refuses_resume(self):
        artifact, plan = self.prepared()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Config sync interrupted')):
            with self.assertRaisesRegex(OSError, 'Config sync interrupted'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        root = Path(plan['to']['objects'])
        retained = root.with_name(root.name + '-old'); root.rename(retained); shutil.copytree(retained, root)
        with self.assertRaisesRegex(ValueError, 'directory identity'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse((Path(plan['to']['workspace']) / 'records/relocations' / plan['id'] / 'switched.json').exists())
