"""Configuration replacement must persist before relocation activation is recorded."""
import os
from pathlib import Path
from unittest.mock import patch
import unittest
import test_relocation_switch as fixtures


class RelocationConfigDurabilityTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def test_parent_directory_is_synced_before_binding_commit(self):
        artifact, plan = self.prepared()
        events = []
        original_sync = os.fsync
        original_replace = os.replace
        original_write = self.store._write_path
        directory = self.store.config_path.parent.stat()
        def sync(fd):
            current = os.fstat(fd)
            if (current.st_dev, current.st_ino) == (directory.st_dev, directory.st_ino):
                events.append('directory-sync')
            return original_sync(fd)
        def replace(source, destination):
            result = original_replace(source, destination)
            if Path(destination) == self.store.config_path:
                events.append('config-replace')
            return result
        def write(path, data):
            if Path(path).parent.name == 'storage-bindings':
                events.append('binding-write')
            return original_write(path, data)
        with patch('relocation_lifecycle.os.fsync', side_effect=sync), patch('relocation_lifecycle.os.replace', side_effect=replace), patch.object(self.store, '_write_path', side_effect=write):
            self.store.switch_relocation(plan['id'], 'owner', 'Durable switch')
        replaced = events.index('config-replace')
        bound = events.index('binding-write')
        self.assertIn('directory-sync', events[replaced + 1:bound])

    def test_resume_retries_directory_sync_when_configuration_already_matches(self):
        from artifact_lifecycle import Lifecycle
        import json
        artifact, plan = self.prepared()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Directory sync failed')):
            with self.assertRaisesRegex(OSError, 'Directory sync failed'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
            moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
            with self.assertRaisesRegex(ValueError, 'inactive'):
                moved.start_run({})
            with self.assertRaisesRegex(OSError, 'Directory sync failed'):
                self.store.resume_relocation(plan['id'], 'owner', 'Retry sync')
        self.assertFalse((Path(plan['to']['workspace']) / 'records/relocations' / plan['id'] / 'switched.json').exists())
        self.store.resume_relocation(plan['id'], 'owner', 'Resume after disk recovery')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        moved.verify_artifact(artifact['id'])
        moved.start_run({})
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_rollback_retries_sync_before_releasing_source_fence(self):
        artifact, plan = self.prepared()
        before = self.store.config_path.read_bytes()
        with patch.object(self.store, '_sync_configuration_directory', side_effect=OSError('Directory sync failed')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
            for reason in ('First rollback', 'Retry rollback'):
                with self.assertRaisesRegex(OSError, 'Directory sync failed'):
                    self.store.rollback_relocation(plan['id'], 'owner', reason)
                self.assertEqual(self.store.config_path.read_bytes(), before)
                with self.assertRaisesRegex(ValueError, 'fenced'):
                    self.store.start_run({})
        self.store.rollback_relocation(plan['id'], 'owner', 'Disk recovered')
        self.store.verify_artifact(artifact['id'])
        self.store.start_run({})
        self.assertTrue(Path(plan['to']['objects']).is_dir())
