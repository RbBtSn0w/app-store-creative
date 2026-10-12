import unittest
import os
from unittest import mock
import test_artifact_lifecycle as fixtures


class RecoveryLockTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_substituted_lock_is_rejected_before_plan_access(self):
        self.store.start_run({})
        lock = self.store.paths.workspace / 'write.lock'
        for method in ('resume_relocation', 'rollback_relocation', 'resume_reverse_relocation', 'rollback_reverse_relocation'):
            with self.subTest(method=method):
                replaced = False
                def acquire(descriptor, operation):
                    nonlocal replaced
                    if not replaced:
                        lock.rename(lock.with_name(method + '-original.lock'))
                        lock.write_bytes(b'new lock owner')
                        replaced = True
                with mock.patch('fcntl.flock', side_effect=acquire):
                    with self.assertRaisesRegex(ValueError, 'lock identity changed'):
                        getattr(self.store, method)('missing-plan', 'owner', 'Recover')
                self.assertEqual(lock.read_bytes(), b'new lock owner')

    def test_missing_lock_is_not_created(self):
        self.store.start_run({})
        lock = self.store.paths.workspace / 'write.lock'
        lock.unlink()
        from relocation_lifecycle import recovery_lock
        with self.assertRaises(FileNotFoundError):
            with recovery_lock(self.store):
                self.fail('Missing authority must not be acquired')
        self.assertFalse(lock.exists())

    def test_nonregular_lock_is_rejected_without_blocking(self):
        self.store.start_run({})
        lock = self.store.paths.workspace / 'write.lock'
        lock.unlink()
        os.mkfifo(lock)
        from relocation_lifecycle import recovery_lock
        with self.assertRaisesRegex(ValueError, 'regular file'):
            with recovery_lock(self.store):
                self.fail('FIFO must not be acquired')
