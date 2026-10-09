"""Restoration intent survives interruptions and excludes destructive purge."""
from pathlib import Path
import json
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_retention_lifecycle as fixtures
import retention_lifecycle

class OrdinaryRestoreIntentTests(unittest.TestCase):
    setUp = fixtures.RetentionTests.setUp
    artifact = fixtures.RetentionTests.artifact

    def quarantine(self):
        _, artifact = self.artifact()
        plan = self.store.plan_cleanup(0)
        return artifact, self.store.quarantine_cleanup(plan['id'], 'owner', 'Isolate')

    def interrupt(self, operation):
        original = retention_lifecycle.os.link
        def interrupted(source, destination):
            if Path(destination).parent.parent == self.store.paths.objects:
                raise OSError('Injected interruption')
            return original(source, destination)
        with patch('retention_lifecycle.os.link', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'Injected'):
                self.store.restore_cleanup(operation['id'], 'owner', 'Restore')

    def test_intent_precedes_object_change(self):
        artifact, operation = self.quarantine()
        self.interrupt(operation)
        self.assertTrue(self.store._path('maintenance', operation['id'], 'restore-intent').is_file())
        self.assertFalse(self.store.object_path(artifact['sha256']).exists())
        status = self.store.maintenance_status(operation['id'])
        self.assertEqual((status['status'], status['phase']), ('INCOMPLETE', 'RESTORING'))
        self.assertFalse(status['execution_verified'])

    def test_resume_preserves_original_intent(self):
        artifact, operation = self.quarantine()
        self.interrupt(operation)
        path = self.store._path('maintenance', operation['id'], 'restore-intent')
        original = path.read_bytes()
        self.store.restore_cleanup(operation['id'], 'another-owner', 'Resume')
        self.assertEqual(path.read_bytes(), original)
        self.store.verify_artifact(artifact['id'])
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'PASS')

    def test_pending_restore_refuses_purge(self):
        _, operation = self.quarantine()
        self.interrupt(operation)
        with self.assertRaisesRegex(ValueError, 'restoration'):
            self.store.plan_purge(operation['id'], 0)

    def test_corrupt_intent_refuses_resume_and_status(self):
        artifact, operation = self.quarantine()
        self.interrupt(operation)
        path = self.store._path('maintenance', operation['id'], 'restore-intent')
        value = json.loads(path.read_text()); value['plan_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.store.restore_cleanup(operation['id'], 'owner', 'Resume')
        self.assertFalse(self.store.object_path(artifact['sha256']).exists())
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'FAIL')

    def test_completed_receipt_without_intent_is_not_backfilled(self):
        _, operation = self.quarantine()
        self.store.restore_cleanup(operation['id'], 'owner', 'Restore')
        path = self.store._path('maintenance', operation['id'], 'restore-intent')
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'no intent'):
            self.store.restore_cleanup(operation['id'], 'owner', 'Resume')
        self.assertFalse(path.exists())
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'FAIL')

    def test_process_death_after_first_object_resumes_original_intent(self):
        artifact, operation = self.quarantine()
        self.store.config_path.write_text(json.dumps(self.cfg))
        scripts = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        code = """
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from artifact_lifecycle import Lifecycle
core = Lifecycle.from_configuration(Path(sys.argv[2]), Path(sys.argv[2])/'creative.config.json')
original = os.link
def interrupted(source, destination):
    result = original(source, destination)
    if Path(destination).parent.parent == core.paths.objects:
        os.kill(os.getpid(), signal.SIGKILL)
    return result
os.link = interrupted
core.restore_cleanup(sys.argv[3], 'owner', 'Process death drill')
"""
        child = subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root), operation['id']], capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr)
        intent = self.store._path('maintenance', operation['id'], 'restore-intent')
        before = intent.read_bytes()
        self.assertFalse(self.store._path('maintenance', operation['id'], 'restored').exists())
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'INCOMPLETE')
        self.store.restore_cleanup(operation['id'], 'owner', 'Resume process death drill')
        self.assertEqual(intent.read_bytes(), before)
        self.store.verify_artifact(artifact['id'])
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'PASS')

    def test_preexisting_purge_plan_is_refused_after_restore_starts(self):
        artifact, operation = self.quarantine()
        plan = self.store.plan_purge(operation['id'], 0)
        self.interrupt(operation)
        with self.assertRaisesRegex(ValueError, 'restoration'):
            self.store.purge_cleanup(plan['id'], 'owner', 'Old plan')
        self.assertTrue(self.store._quarantine_path(operation['id'], artifact['sha256']).is_file())

    def test_intent_sync_failure_preserves_all_object_bytes(self):
        artifact, operation = self.quarantine()
        with patch('operation_history.sync_directory', side_effect=OSError('Injected sync failure')):
            with self.assertRaisesRegex(OSError, 'sync failure'):
                self.store.restore_cleanup(operation['id'], 'owner', 'Restore')
        self.assertFalse(self.store.object_path(artifact['sha256']).exists())
        self.assertTrue(self.store._quarantine_path(operation['id'], artifact['sha256']).is_file())

    def test_missing_retained_copy_invalidates_completed_recovery(self):
        artifact, operation = self.quarantine()
        self.store.restore_cleanup(operation['id'], 'owner', 'Restore')
        self.store._quarantine_path(operation['id'], artifact['sha256']).unlink()
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'FAIL')
        with self.assertRaisesRegex(ValueError, 'retained copy'):
            self.store.restore_cleanup(operation['id'], 'owner', 'Resume')

    def test_intent_write_failure_does_not_restore_objects(self):
        artifact, operation = self.quarantine()
        original = self.store._record
        def failed(category, body, suffix=None):
            if category == 'maintenance' and suffix == 'restore-intent':
                raise OSError('Injected intent write failure')
            return original(category, body, suffix)
        with patch.object(self.store, '_record', side_effect=failed):
            with self.assertRaisesRegex(OSError, 'intent write failure'):
                self.store.restore_cleanup(operation['id'], 'owner', 'Restore')
        self.assertFalse(self.store.object_path(artifact['sha256']).exists())
        self.assertFalse(self.store._path('maintenance', operation['id'], 'restore-intent').exists())
        self.assertTrue(self.store._quarantine_path(operation['id'], artifact['sha256']).is_file())

    def test_corrupt_active_object_is_preserved_and_blocks_resume(self):
        artifact, operation = self.quarantine()
        self.interrupt(operation)
        active = self.store.object_path(artifact['sha256'])
        active.parent.mkdir(parents=True, exist_ok=True)
        active.write_bytes(b'Preserve conflicting bytes')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.restore_cleanup(operation['id'], 'owner', 'Resume')
        self.assertEqual(active.read_bytes(), b'Preserve conflicting bytes')
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'FAIL')

    def test_completed_receipt_hash_tampering_is_rejected(self):
        _, operation = self.quarantine()
        self.store.restore_cleanup(operation['id'], 'owner', 'Restore')
        path = self.store._path('maintenance', operation['id'], 'restored')
        value = json.loads(path.read_text()); value['restore_intent_sha256'] = '0' * 64
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.store.restore_cleanup(operation['id'], 'owner', 'Resume')
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'FAIL')
