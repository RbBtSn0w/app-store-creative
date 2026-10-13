"""Configuration preparation preserves authority and proves staged ownership."""
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import patch
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle
from configuration_layers import plan_storage_change


class ConfigurationPreparationTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    load = fixtures.ConfigurationLayersTests.load
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def prepare(self, identity='change-1'):
        from configuration_preparation import prepare_storage_change
        layers = self.load()
        store = Lifecycle(self.root, self.project, self.path)
        plan = plan_storage_change(layers, {'workspaceRoot':'next work'})
        return prepare_storage_change(store, plan, identity, 'operator', 'Move managed storage')

    def test_shared_preparation_is_private_and_does_not_activate_storage(self):
        before = self.path.read_bytes()
        receipt = self.prepare()
        staged = Path(receipt['staged_path'])
        self.assertEqual(receipt['state'], 'PREPARED')
        self.assertEqual(staged.parent, self.path.parent)
        self.assertEqual(stat.S_IMODE(staged.stat().st_mode), 0o600)
        self.assertEqual(json.loads(staged.read_bytes())['storage'], {'workspaceRoot':'next work'})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / 'next work').exists())
        self.assertEqual(self.prepare(), receipt)

    def test_local_preparation_preserves_both_documents(self):
        self.write_local(storage={})
        before = self.path.read_bytes(), self.local.read_bytes()
        receipt = self.prepare()
        staged = Path(receipt['staged_path'])
        self.assertEqual(receipt['target_path'], str(self.local))
        self.assertEqual(json.loads(staged.read_bytes())['project_id'], 'demo')
        self.assertEqual((self.path.read_bytes(), self.local.read_bytes()), before)

    def test_replaced_staging_is_not_accepted_even_with_same_bytes(self):
        receipt = self.prepare(); staged = Path(receipt['staged_path'])
        other = self.root / 'replacement'; other.write_bytes(staged.read_bytes()); other.chmod(0o600)
        other.replace(staged)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'identity|ownership'): self.prepare()
        self.assertEqual(self.path.read_bytes(), before)

    def test_changed_configuration_blocks_prepared_reuse(self):
        receipt = self.prepare(); before = Path(receipt['staged_path']).read_bytes()
        self.path.write_text(json.dumps({**self.project, 'cards':[{'id':'edited'}]}))
        with self.assertRaisesRegex(ValueError, 'differs|stale'): self.prepare()
        self.assertEqual(Path(receipt['staged_path']).read_bytes(), before)

    def test_git_must_ignore_staging_and_private_journal(self):
        self.git('init','-q')
        with self.assertRaisesRegex(ValueError, 'ignored'): self.prepare()
        self.assertFalse((self.root / 'shared work').exists())
        (self.root / '.gitignore').write_text('/shared work/\n/.*.creative-*.tmp\n')
        receipt = self.prepare()
        self.assertEqual(receipt['state'], 'PREPARED')
        self.assertEqual(self.git('ls-files').stdout, '')
        (self.root / '.gitignore').write_text('/shared work/\n')
        with self.assertRaisesRegex(ValueError, 'ignored'): self.prepare()

    def test_complete_payload_resumes_after_directory_sync_interruption(self):
        import configuration_preparation
        sync = configuration_preparation._sync_directory
        def interrupt_payload_sync(path):
            if path == self.path.parent:
                raise OSError('sync interrupted')
            sync(path)
        with patch.object(configuration_preparation, '_sync_directory', side_effect=interrupt_payload_sync):
            with self.assertRaisesRegex(OSError, 'sync interrupted'): self.prepare()
        staged = self.path.with_name('.creative.config.json.creative-change-1.tmp')
        self.assertEqual(json.loads(staged.read_bytes())['storage'], {'workspaceRoot':'next work'})
        receipt = self.prepare()
        self.assertEqual(receipt['state'], 'PREPARED')
        self.assertFalse((self.root / 'next work').exists())

    def test_partial_payload_is_preserved_and_not_rewritten(self):
        import configuration_preparation
        sync = configuration_preparation._sync_directory
        def interrupt_payload_sync(path):
            if path == self.path.parent:
                raise OSError('sync interrupted')
            sync(path)
        with patch.object(configuration_preparation, '_sync_directory', side_effect=interrupt_payload_sync):
            with self.assertRaises(OSError): self.prepare()
        staged = self.path.with_name('.creative.config.json.creative-change-1.tmp')
        staged.write_bytes(b'{"partial":')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'incomplete|changed'): self.prepare()
        self.assertEqual(staged.read_bytes(), b'{"partial":')
        self.assertEqual(self.path.read_bytes(), before)

    def test_source_change_during_preparation_never_produces_prepared_receipt(self):
        import configuration_preparation
        sync = configuration_preparation._sync_directory
        def edit_source(path):
            sync(path)
            if path == self.path.parent:
                self.path.write_text(json.dumps({**self.project, 'cards':[{'id':'edited'}]}))
        with patch.object(configuration_preparation, '_sync_directory', side_effect=edit_source):
            with self.assertRaisesRegex(ValueError, 'stale|differs'): self.prepare()
        receipt = self.root / 'shared work/records/configuration-changes/change-1/prepared.json'
        self.assertFalse(receipt.exists())
        self.assertEqual(json.loads(self.path.read_bytes())['cards'], [{'id':'edited'}])

    def test_prepared_verification_is_read_only_and_binds_the_whole_plan(self):
        from configuration_preparation import verify_prepared_storage_change
        receipt = self.prepare()
        plan = plan_storage_change(self.load(), {'workspaceRoot':'next work'})
        store = Lifecycle(self.root, self.project, self.path)
        before = {p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(verify_prepared_storage_change(store, plan, 'change-1'), receipt)
        self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        with self.assertRaisesRegex(ValueError, 'stale|differs'):
            verify_prepared_storage_change(store, {**plan, 'target_revision':'edited'}, 'change-1')

    def test_prepared_verification_refuses_missing_or_substituted_payload(self):
        from configuration_preparation import verify_prepared_storage_change
        receipt = self.prepare()
        plan = plan_storage_change(self.load(), {'workspaceRoot':'next work'})
        store = Lifecycle(self.root, self.project, self.path)
        staged = Path(receipt['staged_path']); replacement = self.root / 'replacement'
        replacement.write_bytes(staged.read_bytes()); replacement.chmod(0o600); replacement.replace(staged)
        with self.assertRaisesRegex(ValueError, 'identity|changed'):
            verify_prepared_storage_change(store, plan, 'change-1')
        staged.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            verify_prepared_storage_change(store, plan, 'change-1')

    def test_prepared_verification_rejects_edited_receipt_and_created_record(self):
        from configuration_preparation import verify_prepared_storage_change
        receipt = self.prepare()
        plan = plan_storage_change(self.load(), {'workspaceRoot':'next work'})
        store = Lifecycle(self.root, self.project, self.path)
        path = store._path('configuration-changes', 'change-1', 'prepared')
        original = path.read_bytes(); data = json.loads(original)
        data['target_path'] = str(self.root / 'arbitrary.json'); path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'differs|invalid'):
            verify_prepared_storage_change(store, plan, 'change-1')
        path.write_bytes(original)
        created = store._path('configuration-changes', 'change-1', 'created')
        data = json.loads(created.read_bytes()); data['identity']['inode'] += 1; created.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'identity|ownership'):
            verify_prepared_storage_change(store, plan, 'change-1')
        self.assertFalse((self.root / 'arbitrary.json').exists())

    def test_prepared_verification_requires_receipt_before_accepting_complete_payload(self):
        from configuration_preparation import verify_prepared_storage_change
        receipt = self.prepare()
        plan = plan_storage_change(self.load(), {'workspaceRoot':'next work'})
        store = Lifecycle(self.root, self.project, self.path)
        store._path('configuration-changes', 'change-1', 'prepared').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            verify_prepared_storage_change(store, plan, 'change-1')
        self.assertTrue(Path(receipt['staged_path']).exists())

    def test_all_journal_records_require_git_protection_before_any_write(self):
        self.git('init','-q')
        (self.root / '.gitignore').write_text('/shared work/\n/.*.creative-*.tmp\n')
        self.git('add', '-f', 'creative.config.json')
        # An exact force-tracked journal defeats ignore protection even under an ignored workspace.
        journal = self.root / 'shared work/records/configuration-changes/change-1/created.json'
        journal.parent.mkdir(parents=True); journal.write_text('{}')
        self.git('add', '-f', str(journal.relative_to(self.root)))
        journal.unlink()
        with self.assertRaisesRegex(ValueError, 'tracked'): self.prepare()
        self.assertFalse(self.path.with_name('.creative.config.json.creative-change-1.tmp').exists())
        self.assertFalse((journal.parent / 'intent.json').exists())

    def test_prepared_verification_refuses_git_protection_loss(self):
        from configuration_preparation import verify_prepared_storage_change
        self.git('init','-q')
        (self.root / '.gitignore').write_text('/shared work/\n/.*.creative-*.tmp\n')
        receipt = self.prepare(); staged = Path(receipt['staged_path']); before = staged.read_bytes()
        plan = plan_storage_change(self.load(), {'workspaceRoot':'next work'})
        (self.root / '.gitignore').write_text('/shared work/\n')
        with self.assertRaisesRegex(ValueError, 'ignored'):
            verify_prepared_storage_change(Lifecycle(self.root, self.project, self.path), plan, 'change-1')
        self.assertEqual(staged.read_bytes(), before)
