"""Forward recovery must reuse owned roots and preserve unexpected evidence."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class RelocationResumeTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def interrupted(self):
        artifact, plan = self.prepared()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Config failed')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        return artifact, plan

    def test_resume_completes_configuration_and_binding_commit(self):
        artifact, plan = self.interrupted()
        receipt = self.store.resume_relocation(plan['id'], 'owner', 'Resume switch')
        self.assertEqual(receipt['status'], 'SWITCHED')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        moved.verify_artifact(artifact['id']); moved.start_run({})
        self.assertEqual(self.store.resume_relocation(plan['id'], 'owner', 'Repeat'), receipt)

    def test_partial_root_publication_resumes_remaining_owned_roots(self):
        artifact, plan = self.prepared()
        from delivery_lifecycle import commit_directory
        published = []
        def fail_second(source, destination):
            if published:
                raise OSError('Next root failed')
            commit_directory(source, destination); published.append(Path(destination))
        with patch('delivery_lifecycle.commit_directory', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        moved.verify_artifact(artifact['id']); moved.start_run({})

    def test_unknown_target_file_blocks_resume_without_deletion(self):
        _, plan = self.interrupted()
        unknown = Path(plan['to']['workspace']) / 'unknown'; unknown.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
        self.assertEqual(unknown.read_bytes(), b'keep')
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.start_run({})

    def test_changed_switch_configuration_evidence_blocks_resume(self):
        _, plan = self.interrupted()
        path = self.store._path('relocations', plan['id'], 'switch-intent')
        intent = json.loads(path.read_text()); intent['target_config']['headline'] = 'Changed evidence'
        path.write_text(json.dumps(intent))
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.resume_relocation(plan['id'], 'owner', 'Resume')
