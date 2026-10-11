"""Failed relocation copies retain evidence and recover through fresh batches."""
from pathlib import Path
from unittest.mock import patch
import unittest
import test_relocation_lifecycle as fixtures


class RelocationRecoveryTests(unittest.TestCase):
    setUp = fixtures.RelocationTests.setUp
    source = fixtures.RelocationTests.source
    targets = fixtures.RelocationTests.targets

    def failed(self):
        artifact = self.source(); plan = self.store.plan_relocation(self.targets())
        with patch('relocation_lifecycle.shutil.copyfileobj', side_effect=OSError('Copy interrupted')):
            with self.assertRaises(OSError):
                self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        return artifact, plan

    def test_recovery_creates_new_batch_without_overwriting_failed_staging(self):
        artifact, plan = self.failed()
        intent = self.store._read('relocations', plan['id'], 'prepare-intent')
        stage = Path(next(iter(intent['staging'].values())))
        unknown = stage / 'partial-note'; unknown.write_text('preserve failed evidence')
        recovered = self.store.recover_relocation(plan['id'], actor='owner', reason='Retry failed copy')
        self.assertNotEqual(recovered['retry_plan_id'], plan['id'])
        self.assertEqual(recovered['status'], 'RECOVERY_PLANNED')
        prepared = self.store.prepare_relocation(recovered['retry_plan_id'], actor='owner', reason='Retry')
        self.assertEqual(prepared['status'], 'PREPARED')
        self.assertEqual(unknown.read_text(), 'preserve failed evidence')
        self.store.verify_artifact(artifact['id'])
        self.assertEqual(self.store.recover_relocation(plan['id'], actor='owner', reason='Repeat')['retry_plan_id'], recovered['retry_plan_id'])

    def test_cancel_prepared_removes_only_owned_verified_staging(self):
        artifact = self.source(); plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        result = self.store.cancel_relocation(plan['id'], actor='owner', reason='Keep current location')
        self.assertEqual(result['status'], 'CANCELLED')
        for root in prepared['staging'].values():
            self.assertFalse(Path(root).exists())
        self.store.verify_artifact(artifact['id'])
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Restart')

    def test_cancel_retains_unknown_and_modified_files(self):
        artifact = self.source(); plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        payload = next(Path(item['path']) for item in prepared['staged_files'] if Path(item['path']).name != '.relocation-owner.json')
        payload.write_bytes(b'modified')
        root = Path(next(iter(prepared['staging'].values())))
        unknown = root / 'unknown'; unknown.write_text('keep')
        result = self.store.cancel_relocation(plan['id'], actor='owner', reason='Cancel safely')
        self.assertEqual(result['status'], 'CANCELLED_PARTIAL')
        self.assertIn(str(payload), result['retained_paths'])
        self.assertIn(str(unknown), result['retained_paths'])
        self.assertEqual(payload.read_bytes(), b'modified')
        self.assertEqual(unknown.read_text(), 'keep')
        self.store.verify_artifact(artifact['id'])

    def test_cancel_refuses_missing_ownership_marker_before_deleting_anything(self):
        self.source(); plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        root = Path(next(iter(prepared['staging'].values())))
        (root / '.relocation-owner.json').unlink()
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.store.cancel_relocation(plan['id'], actor='owner', reason='Cancel')
        self.assertTrue(any(Path(item['path']).exists() for item in prepared['staged_files'] if Path(item['path']).name != '.relocation-owner.json'))

    def test_stale_source_blocks_recovery(self):
        artifact, plan = self.failed()
        (self.store.paths.workspace / artifact['workspace_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.store.recover_relocation(plan['id'], actor='owner', reason='Retry')

    def test_cancel_preserves_unknown_symlink_and_external_target(self):
        self.source(); plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        root = Path(next(iter(prepared['staging'].values())))
        external = root.parent / 'external-evidence'; external.write_text('untouched')
        link = root / 'external-link'; link.symlink_to(external)
        result = self.store.cancel_relocation(plan['id'], actor='owner', reason='Cancel')
        self.assertEqual(result['status'], 'CANCELLED_PARTIAL')
        self.assertIn(str(link), result['retained_paths'])
        self.assertTrue(link.is_symlink())
        self.assertEqual(external.read_text(), 'untouched')
        self.assertEqual(self.store.cancel_relocation(plan['id'], actor='owner', reason='Repeat'), result)

    def test_copy_refuses_destination_created_after_initial_check(self):
        import os
        self.source(); plan = self.store.plan_relocation(self.targets())
        original_open = os.open
        raced = []
        def racing_open(path, flags, *args, **kwargs):
            path = Path(path)
            if flags & os.O_EXCL and '.creative-relocate-' in str(path) and path.name != '.relocation-owner.json' and not raced:
                path.write_bytes(b'concurrent evidence'); raced.append(path)
            return original_open(path, flags, *args, **kwargs)
        with patch('relocation_lifecycle.os.open', side_effect=racing_open):
            with self.assertRaises(FileExistsError):
                self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        self.assertEqual(raced[0].read_bytes(), b'concurrent evidence')
        self.assertEqual(self.store._read('relocations', plan['id'], 'prepare-outcome')['status'], 'PREPARATION_FAILED')

    def test_cancel_refuses_same_byte_replaced_staging_directory(self):
        import shutil
        import json
        self.store.config_path.write_text(json.dumps(self.cfg))
        self.source(); plan = self.store.plan_relocation(self.targets())
        self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        prepared = self.store._read('relocations', plan['id'], 'prepared')
        root = Path(prepared['staging']['objects'])
        retained = root.with_name(root.name + '-retained')
        root.rename(retained); shutil.copytree(retained, root)
        before = {str(path): path.read_bytes() for directory in (root, retained)
                  for path in directory.rglob('*') if path.is_file()}
        with self.assertRaisesRegex(ValueError, 'identity|ownership'):
            self.store.cancel_relocation(plan['id'], 'owner', 'Preserve replaced directory')
        self.assertEqual(before, {str(path): path.read_bytes() for directory in (root, retained)
                                 for path in directory.rglob('*') if path.is_file()})
        import subprocess
        import sys
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'storage', 'cancel-relocate',
            '--repo', str(self.root), '--id', plan['id'], '--actor', 'owner',
            '--reason', 'Preserve replaced directory', '--confirm', 'CANCEL'],
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('directory identity changed', result.stderr)
        self.assertEqual(before, {str(path): path.read_bytes() for directory in (root, retained)
                                 for path in directory.rglob('*') if path.is_file()})

    def test_cancel_refuses_root_replacement_after_intent_commit(self):
        import shutil
        self.source(); plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        root = Path(prepared['staging']['objects'])
        retained = root.with_name(root.name + '-retained')
        recorded = self.store._record
        before = {}
        def replace_after_intent(category, data, suffix=None):
            result = recorded(category, data, suffix)
            if category == 'relocations' and suffix == 'cancel-intent':
                root.rename(retained); shutil.copytree(retained, root)
                before.update({str(path): path.read_bytes() for directory in (root, retained)
                               for path in directory.rglob('*') if path.is_file()})
            return result
        with patch.object(self.store, '_record', side_effect=replace_after_intent):
            with self.assertRaisesRegex(ValueError, 'identity|ownership'):
                self.store.cancel_relocation(plan['id'], 'owner', 'Preserve replaced staging')
        self.assertTrue(before)
        self.assertEqual(before, {str(path): path.read_bytes() for directory in (root, retained)
                                 for path in directory.rglob('*') if path.is_file()})
        self.assertFalse(self.store._path('relocations', plan['id'], 'cancelled').exists())
