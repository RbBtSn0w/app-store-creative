"""Reverse switching and resume use the unified configuration inode evidence."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_reverse_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class ReverseConfigurationInstallationTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationSwitchTests.setUp
    source = fixtures.ReverseRelocationSwitchTests.source
    targets = fixtures.ReverseRelocationSwitchTests.targets
    prepared = fixtures.ReverseRelocationSwitchTests.prepared
    moved = fixtures.ReverseRelocationSwitchTests.moved
    reverse = fixtures.ReverseRelocationSwitchTests.reverse

    def test_reverse_preparation_and_installation_evidence_reach_returned_workspace(self):
        artifact, _, moved, reverse, _ = self.reverse()
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        proof = moved._read('relocations', reverse['id'], 'configuration-installation')
        prepared = moved._read('relocations', reverse['id'], 'configuration-prepared')
        self.assertEqual(proof['installed_identity']['inode'], moved.config_path.stat().st_ino)
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_bytes()))
        self.assertEqual(returned._read('relocations', reverse['id'], 'configuration-installation'), proof)
        self.assertEqual(returned._read('relocations', reverse['id'], 'configuration-prepared'), prepared)
        returned.verify_artifact(artifact['id'])

    def test_reverse_installed_interruption_resumes_with_its_own_inode(self):
        artifact, _, moved, reverse, _ = self.reverse()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Installed sync interrupted')):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        proof = moved._read('relocations', reverse['id'], 'configuration-installation')
        self.assertEqual(proof['installed_identity']['inode'], moved.config_path.stat().st_ino)
        moved.resume_reverse_relocation(reverse['id'], 'owner', 'Resume')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_bytes()))
        returned.verify_artifact(artifact['id']); returned.start_run({})

    def test_substituted_reverse_installed_inode_refuses_resume(self):
        _, _, moved, reverse, _ = self.reverse()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Installed sync interrupted')):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        before = moved.config_path.read_bytes(); replacement = self.root / 'substitute'
        replacement.write_bytes(before); replacement.replace(moved.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            moved.resume_reverse_relocation(reverse['id'], 'owner', 'Resume')
        self.assertEqual(moved.config_path.read_bytes(), before)
        self.assertFalse(moved._path('relocations', reverse['id'], 'switched').exists())

    def test_source_substitution_during_exchange_refuses_reverse_configuration_write(self):
        import delivery_lifecycle
        _, _, moved, reverse, _ = self.reverse(); before = moved.config_path.read_bytes()
        apply = delivery_lifecycle.apply_directory_change
        def replace_source(change):
            result = apply(change)
            replacement = self.root / 'replacement'; replacement.write_bytes(before)
            replacement.replace(moved.config_path)
            return result
        with patch.object(delivery_lifecycle, 'apply_directory_change', side_effect=replace_source):
            with self.assertRaisesRegex(ValueError, 'stale|differs|identity'):
                moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        self.assertEqual(moved.config_path.read_bytes(), before)

    def test_reverse_git_policy_covers_actual_configuration_switch(self):
        import subprocess
        artifact, _, moved, reverse, _ = self.reverse()
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        policy = moved.relocation_git_policy(reverse['id'])
        self.assertIn('configuration_installation_staging', policy)
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return')
        returned = Lifecycle(self.root, json.loads(moved.config_path.read_bytes()))
        returned.verify_artifact(artifact['id']); returned.start_run({})
        self.assertEqual(subprocess.check_output(['git', '-C', str(self.root), 'ls-files']), b'')
