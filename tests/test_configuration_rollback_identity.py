"""Rollback preserves external replacements and proves its own restoration inode."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_rollback as fixtures


class ConfigurationRollbackIdentityTests(unittest.TestCase):
    setUp = fixtures.RelocationRollbackTests.setUp
    source = fixtures.RelocationRollbackTests.source
    targets = fixtures.RelocationRollbackTests.targets
    prepared = fixtures.RelocationRollbackTests.prepared
    interrupted = fixtures.RelocationRollbackTests.interrupted

    def replaced_interruption(self):
        artifact, plan = self.prepared(); original = self.store.config_path.read_bytes()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Installed sync interrupted')):
            with self.assertRaises(OSError): self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        return artifact, plan, original

    def test_replaced_source_inode_blocks_rollback_before_intent(self):
        _, plan, _ = self.interrupted(); before = self.store.config_path.read_bytes()
        replacement = self.root / 'replacement'; replacement.write_bytes(before); replacement.replace(self.store.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|stale|differs'):
            self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertFalse(self.store._path('relocations', plan['id'], 'rollback-intent').exists())

    def test_replaced_installed_inode_is_not_overwritten_by_rollback(self):
        _, plan, _ = self.replaced_interruption(); before = self.store.config_path.read_bytes()
        replacement = self.root / 'replacement'; replacement.write_bytes(before); replacement.replace(self.store.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertFalse(self.store._path('relocations', plan['id'], 'rollback-intent').exists())

    def test_restored_inode_proof_allows_retry_after_rollback_sync_interruption(self):
        artifact, plan, original = self.replaced_interruption()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Rollback sync interrupted')):
            with self.assertRaises(OSError): self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        proof = self.store._read('relocations', plan['id'], 'configuration-rollback-installation')
        self.assertEqual(proof['installed_identity']['inode'], self.store.config_path.stat().st_ino)
        self.assertEqual(self.store.config_path.read_bytes(), original)
        self.store.rollback_relocation(plan['id'], 'owner', 'Retry rollback')
        self.store.verify_artifact(artifact['id']); self.store.start_run({})

    def test_same_bytes_at_substituted_restored_inode_block_retry(self):
        _, plan, original = self.replaced_interruption()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Rollback sync interrupted')):
            with self.assertRaises(OSError): self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        replacement = self.root / 'replacement'; replacement.write_bytes(original); replacement.replace(self.store.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            self.store.rollback_relocation(plan['id'], 'owner', 'Retry rollback')
        self.assertFalse(self.store._path('relocations', plan['id'], 'rollback').exists())

    def test_git_suggestions_cover_restore_and_rollback_after_installed_interruption(self):
        import subprocess
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        artifact = self.source(); self.store.config_path.write_text(json.dumps(self.cfg))
        original = self.store.config_path.read_bytes()
        plan = self.store.plan_relocation(self.targets())
        policy = self.store.relocation_git_policy(plan['id'])
        self.assertIn('configuration_restoration_staging', policy)
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError): self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        self.assertEqual(self.store.config_path.read_bytes(), original)
        self.store.verify_artifact(artifact['id'])

    def test_restore_temporary_substitution_blocks_retry_without_overwrite(self):
        _, plan, _ = self.replaced_interruption(); target = self.store.config_path.read_bytes()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Restore interrupted')):
            with self.assertRaises(OSError): self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        proof = self.store._read('relocations', plan['id'], 'configuration-rollback-installation')
        temporary = Path(proof['temporary_path']); replacement = self.root / 'replacement'
        replacement.write_bytes(temporary.read_bytes()); replacement.chmod(temporary.stat().st_mode & 0o777)
        replacement.replace(temporary)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            self.store.rollback_relocation(plan['id'], 'owner', 'Retry rollback')
        self.assertEqual(self.store.config_path.read_bytes(), target)
        self.assertFalse(self.store._path('relocations', plan['id'], 'rollback').exists())

    def test_source_identity_is_rechecked_after_media_validation(self):
        _, plan, original = self.interrupted()
        snapshot = self.store._relocation_snapshot
        def replace_source_after_snapshot(*args, **kwargs):
            result = snapshot(*args, **kwargs)
            replacement = self.root / 'replacement'; replacement.write_bytes(original)
            replacement.replace(self.store.config_path)
            return result
        with patch.object(self.store, '_relocation_snapshot', side_effect=replace_source_after_snapshot):
            with self.assertRaisesRegex(ValueError, 'identity|stale|differs'):
                self.store.rollback_relocation(plan['id'], 'owner', 'Rollback')
        self.assertFalse(self.store._path('relocations', plan['id'], 'rollback').exists())
        self.assertEqual(self.store.config_path.read_bytes(), original)
