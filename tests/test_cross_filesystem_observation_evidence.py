"""Opt-in raw observation and summary recovery on an independent test volume."""
import os
from pathlib import Path
import tempfile
import unittest
import test_remote_observations as fixtures


class CrossFilesystemObservationEvidenceTests(unittest.TestCase):
    plan = fixtures.RemoteObservationTests.plan
    observe = fixtures.RemoteObservationTests.observe
    git = fixtures.RemoteObservationTests.git
    persist = fixtures.RemoteObservationTests.persist
    evidence_relocation_crash_case = fixtures.RemoteObservationTests.evidence_relocation_crash_case

    def setUp(self):
        value = os.environ.get('CREATIVE_TEST_CROSSFS_ROOT')
        if not value:
            self.skipTest('Explicit independently mounted test volume required')
        volume = Path(value).resolve(strict=True)
        fixtures.RemoteObservationTests.setUp(self)
        if volume.stat().st_dev == self.root.stat().st_dev:
            self.skipTest('Requested test volume shares the source filesystem')
        owned = tempfile.TemporaryDirectory(prefix='creative-evidence-owned-', dir=volume)
        self.addCleanup(owned.cleanup)
        destination = Path(owned.name)
        self.assertNotEqual(destination.stat().st_dev, self.root.stat().st_dev)
        original = self.store.plan_relocation

        def plan(targets, *args, **kwargs):
            return original({key: str(destination / Path(value).name)
                             for key, value in targets.items()}, *args, **kwargs)

        self.store.plan_relocation = plan

    test_evidence_forward_intent_sigkill_resume = fixtures.RemoteObservationTests.test_evidence_forward_intent_sigkill_resume

    test_evidence_forward_intent_sigkill_rollback = fixtures.RemoteObservationTests.test_evidence_forward_intent_sigkill_rollback

    test_evidence_forward_receipt_sigkill_resume = fixtures.RemoteObservationTests.test_evidence_forward_receipt_sigkill_resume

    test_evidence_forward_receipt_sigkill_rollback = fixtures.RemoteObservationTests.test_evidence_forward_receipt_sigkill_rollback

    test_evidence_relocation_directory_sigkill_resumes_through_public_cli = fixtures.RemoteObservationTests.test_evidence_relocation_directory_sigkill_resumes_through_public_cli

    test_evidence_relocation_directory_sigkill_rolls_back_through_public_cli = fixtures.RemoteObservationTests.test_evidence_relocation_directory_sigkill_rolls_back_through_public_cli

    test_evidence_relocation_sigkill_resumes_through_public_cli = fixtures.RemoteObservationTests.test_evidence_relocation_sigkill_resumes_through_public_cli

    test_evidence_relocation_sigkill_rolls_back_through_public_cli = fixtures.RemoteObservationTests.test_evidence_relocation_sigkill_rolls_back_through_public_cli

    test_evidence_reverse_intent_sigkill_resume = fixtures.RemoteObservationTests.test_evidence_reverse_intent_sigkill_resume

    test_evidence_reverse_intent_sigkill_rollback = fixtures.RemoteObservationTests.test_evidence_reverse_intent_sigkill_rollback

    test_evidence_reverse_receipt_sigkill_resume = fixtures.RemoteObservationTests.test_evidence_reverse_receipt_sigkill_resume

    test_evidence_reverse_receipt_sigkill_rollback = fixtures.RemoteObservationTests.test_evidence_reverse_receipt_sigkill_rollback

    test_reverse_evidence_relocation_configuration_sigkill_resumes = fixtures.RemoteObservationTests.test_reverse_evidence_relocation_configuration_sigkill_resumes

    test_reverse_evidence_relocation_configuration_sigkill_rolls_back = fixtures.RemoteObservationTests.test_reverse_evidence_relocation_configuration_sigkill_rolls_back

    test_reverse_evidence_relocation_directory_sigkill_resumes = fixtures.RemoteObservationTests.test_reverse_evidence_relocation_directory_sigkill_resumes

    test_reverse_evidence_relocation_directory_sigkill_rolls_back = fixtures.RemoteObservationTests.test_reverse_evidence_relocation_directory_sigkill_rolls_back
