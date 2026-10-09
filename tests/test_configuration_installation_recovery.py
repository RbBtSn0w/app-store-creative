"""A pre-replacement inode proof distinguishes installation from substitution."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class ConfigurationInstallationRecoveryTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def installed_interruption(self):
        artifact, plan = self.prepared()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertEqual(json.loads(self.store.config_path.read_bytes())['storage'], self.targets())
        return artifact, plan

    def test_installed_identity_is_recorded_before_replace_and_transferred_on_resume(self):
        artifact, plan = self.installed_interruption()
        proof = self.store._read('relocations', plan['id'], 'configuration-installation')
        self.assertEqual(proof['installed_identity']['inode'], self.store.config_path.stat().st_ino)
        self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_bytes()))
        self.assertEqual(moved._read('relocations', plan['id'], 'configuration-installation'), proof)
        moved.verify_artifact(artifact['id'])

    def test_same_bytes_at_substituted_installed_identity_are_refused(self):
        artifact, plan = self.installed_interruption(); before = self.store.config_path.read_bytes()
        replacement = self.root / 'substitute.json'; replacement.write_bytes(before)
        replacement.replace(self.store.config_path)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'resume-intent').exists())
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_missing_installation_proof_does_not_authorize_target_bytes(self):
        _, plan = self.installed_interruption()
        proof = self.store._path('relocations', plan['id'], 'configuration-installation')
        self.assertTrue(proof.exists()); proof.unlink()
        with self.assertRaises((FileNotFoundError, ValueError)):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'resume-intent').exists())

    def test_recovery_refuses_replaced_uninstalled_temporary_inode(self):
        _, plan = self.prepared()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Replace interrupted')):
            with self.assertRaises(OSError): self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        proof = self.store._read('relocations', plan['id'], 'configuration-installation')
        temporary = Path(proof['temporary_path']); before = self.store.config_path.read_bytes()
        replacement = self.root / 'replacement'; replacement.write_bytes(temporary.read_bytes())
        replacement.chmod(temporary.stat().st_mode & 0o777); replacement.replace(temporary)
        with self.assertRaisesRegex(ValueError, 'identity|installation'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(self.store.config_path.read_bytes(), before)

    def test_record_sync_interruption_is_resynchronized_before_resume_replace(self):
        import configuration_installation
        import os
        _, plan = self.prepared()
        record_parent = self.store._path('relocations', plan['id'], 'configuration-installation').parent
        sync = configuration_installation._sync_directory
        def fail_record_sync(path):
            if path == record_parent: raise OSError('Record sync interrupted')
            sync(path)
        with patch.object(configuration_installation, '_sync_directory', side_effect=fail_record_sync):
            with self.assertRaisesRegex(OSError, 'Record sync interrupted'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        observed = []
        replace = os.replace
        def track_sync(path):
            sync(path)
            if path == record_parent: observed.append('proof-sync')
        def track_replace(source, target):
            self.assertIn('proof-sync', observed)
            return replace(source, target)
        with patch.object(configuration_installation, '_sync_directory', side_effect=track_sync), patch('relocation_lifecycle.os.replace', side_effect=track_replace):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
