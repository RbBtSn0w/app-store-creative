"""Interrupted forward recovery retains configuration preparation authority."""
import json
from pathlib import Path
import unittest
import test_relocation_resume as fixtures


class RelocationConfigurationResumeTests(unittest.TestCase):
    setUp = fixtures.RelocationResumeTests.setUp
    source = fixtures.RelocationResumeTests.source
    targets = fixtures.RelocationResumeTests.targets
    prepared = fixtures.RelocationResumeTests.prepared
    interrupted = fixtures.RelocationResumeTests.interrupted

    def test_replaced_source_configuration_blocks_resume_before_new_records(self):
        artifact, plan = self.interrupted(); before = self.store.config_path.read_bytes()
        replacement = self.root / 'replacement.json'; replacement.write_bytes(before)
        replacement.replace(self.store.config_path)
        with self.assertRaisesRegex(ValueError, 'stale|differs|identity'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'resume-intent').exists())
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_substituted_staging_blocks_resume_without_configuration_write(self):
        _, plan = self.interrupted(); before = self.store.config_path.read_bytes()
        proof = self.store._read('relocations', plan['id'], 'configuration-prepared')
        staged = Path(proof['staged_path']); replacement = self.root / 'replacement'
        replacement.write_bytes(staged.read_bytes()); replacement.chmod(0o600); replacement.replace(staged)
        with self.assertRaisesRegex(ValueError, 'identity|ownership|changed'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'resume-intent').exists())
        self.assertEqual(self.store.config_path.read_bytes(), before)

    def test_switch_intent_must_reference_exact_preparation_receipt(self):
        _, plan = self.interrupted(); before = self.store.config_path.read_bytes()
        path = self.store._path('relocations', plan['id'], 'switch-intent')
        intent = json.loads(path.read_bytes()); intent['configuration_prepared']['target_revision'] = 'edited'
        path.write_text(json.dumps(intent))
        with self.assertRaisesRegex(ValueError, 'evidence|receipt|differs'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertFalse(self.store._path('relocations', plan['id'], 'resume-intent').exists())
        self.assertEqual(self.store.config_path.read_bytes(), before)
