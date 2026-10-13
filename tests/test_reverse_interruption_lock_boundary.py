"""Reverse switch failure evidence remains within the operation lock."""
from contextlib import contextmanager
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
from relocation_lifecycle import RelocationOperations


class ReverseInterruptionLockBoundaryTests(unittest.TestCase):
    def test_switch_records_interruption_before_releasing_lock(self):
        locked = [False]
        @contextmanager
        def transaction():
            locked[0] = True
            try: yield
            finally: locked[0] = False
        def fail(*args): raise ValueError('forced validation failure')
        core = SimpleNamespace(transaction=transaction, _verify_reverse_relocation_locked=fail)
        observations = []
        with patch('reverse_relocation.record_interruption', side_effect=lambda *args: observations.append(locked[0])):
            with self.assertRaisesRegex(ValueError, 'forced'):
                RelocationOperations.switch_reverse_relocation(core, 'plan', 'owner', 'switch')
        self.assertEqual(observations, [True])

    def test_rollback_failure_is_not_recorded_as_switch_interruption(self):
        with patch('reverse_relocation.rollback', side_effect=ValueError('forced rollback')), \
             patch('reverse_relocation.record_interruption') as record:
            with self.assertRaisesRegex(ValueError, 'forced rollback'):
                RelocationOperations.rollback_reverse_relocation(SimpleNamespace(), 'plan', 'owner', 'rollback')
            record.assert_not_called()

    def test_resume_records_interruption_inside_recovery_lock(self):
        locked = [False]
        @contextmanager
        def recovery_lock(core):
            locked[0] = True
            try: yield
            finally: locked[0] = False
        def fail(*args): raise ValueError('forced recovery failure')
        core = SimpleNamespace(_read=fail)
        observations = []
        with patch('relocation_lifecycle.recovery_lock', recovery_lock), \
             patch('reverse_relocation.record_interruption', side_effect=lambda *args: observations.append(locked[0])):
            with self.assertRaisesRegex(ValueError, 'forced recovery'):
                RelocationOperations.resume_reverse_relocation(core, 'plan', 'owner', 'resume')
        self.assertEqual(observations, [True])
