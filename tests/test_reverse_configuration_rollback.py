"""Reverse rollback refuses external inode substitution and proves restoration."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_reverse_relocation_rollback as fixtures


class ReverseConfigurationRollbackTests(unittest.TestCase):
    setUp = fixtures.ReverseRollbackTests.setUp
    source = fixtures.ReverseRollbackTests.source
    targets = fixtures.ReverseRollbackTests.targets
    prepared = fixtures.ReverseRollbackTests.prepared
    moved = fixtures.ReverseRollbackTests.moved
    reverse = fixtures.ReverseRollbackTests.reverse
    interrupted = fixtures.ReverseRollbackTests.interrupted

    def installed_interruption(self):
        artifact, forward, moved, reverse, run = self.reverse(); before = moved.config_path.read_bytes()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Installed sync interrupted')):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        return artifact, forward, moved, reverse, run, before

    def test_source_substitution_blocks_reverse_rollback_before_intent_and_exchange(self):
        _, _, moved, reverse, _, before = self.interrupted()
        root = Path(self.changed_root['destination']); identity = root.stat().st_ino
        replacement = self.root / 'replacement'; replacement.write_bytes(before); replacement.replace(moved.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|stale|differs'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
        self.assertFalse(moved._path('relocations', reverse['id'], 'rollback-intent').exists())
        self.assertEqual(root.stat().st_ino, identity)

    def test_installed_substitution_is_preserved_and_refuses_reverse_rollback(self):
        _, _, moved, reverse, _, _ = self.installed_interruption(); before = moved.config_path.read_bytes()
        replacement = self.root / 'replacement'; replacement.write_bytes(before); replacement.replace(moved.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
        self.assertFalse(moved._path('relocations', reverse['id'], 'rollback-intent').exists())
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_restoration_sync_interruption_reuses_own_restored_inode(self):
        artifact, _, moved, reverse, run, before = self.installed_interruption()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Restore sync interrupted')):
            with self.assertRaises(OSError): moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
        proof = moved._read('relocations', reverse['id'], 'configuration-rollback-installation')
        self.assertEqual(proof['installed_identity']['inode'], moved.config_path.stat().st_ino)
        self.assertEqual(moved.config_path.read_bytes(), before)
        moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Retry')
        moved.verify_artifact(artifact['id']); moved._run(run['id']); moved.start_run({})

    def test_restored_substitution_blocks_retry_without_releasing_fence(self):
        _, _, moved, reverse, _, before = self.installed_interruption()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Restore sync interrupted')):
            with self.assertRaises(OSError): moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
        replacement = self.root / 'replacement'; replacement.write_bytes(before); replacement.replace(moved.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Retry')
        self.assertFalse(moved._path('relocations', reverse['id'], 'rollback').exists())
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_source_replaced_during_directory_revert_refuses_completion(self):
        import delivery_lifecycle
        _, _, moved, reverse, _, before = self.interrupted()
        revert = delivery_lifecycle.revert_directory_change
        def substitute_source(change):
            result = revert(change)
            replacement = self.root / 'replacement'; replacement.write_bytes(before)
            replacement.replace(moved.config_path)
            return result
        with patch.object(delivery_lifecycle, 'revert_directory_change', side_effect=substitute_source):
            with self.assertRaisesRegex(ValueError, 'identity|stale|differs'):
                moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Rollback')
        self.assertFalse(moved._path('relocations', reverse['id'], 'rollback').exists())
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_git_suggestions_cover_reverse_restoration(self):
        import subprocess
        artifact, _, moved, reverse, _, before = self.reverse_with_git()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Installed sync interrupted')):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        moved.rollback_reverse_relocation(reverse['id'], 'owner', 'Keep source')
        self.assertEqual(moved.config_path.read_bytes(), before)
        moved.verify_artifact(artifact['id']); moved.start_run({})
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.root), 'ls-files']), b'')

    def reverse_with_git(self):
        import subprocess
        artifact, forward, moved, reverse, run = self.reverse(); before = moved.config_path.read_bytes()
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        policy = moved.relocation_git_policy(reverse['id'])
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        return artifact, forward, moved, reverse, run, before
