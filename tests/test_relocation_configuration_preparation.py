"""Forward switching consumes the owning configuration preparation evidence."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class RelocationConfigurationPreparationTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def test_switch_records_preparation_and_copies_evidence_to_target(self):
        artifact, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        intent = self.store._read('relocations', plan['id'], 'switch-intent')
        self.assertIn('configuration_prepared', intent)
        proof = self.store._read('relocations', plan['id'], 'configuration-prepared')
        self.assertEqual(intent['configuration_prepared'], proof)
        self.assertEqual(proof['state'], 'PREPARED')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_bytes()))
        self.assertEqual(moved._read('relocations', plan['id'], 'configuration-prepared'), proof)
        moved.verify_artifact(artifact['id'])

    def test_source_identity_change_after_publish_blocks_configuration_replacement(self):
        import delivery_lifecycle
        artifact, plan = self.prepared(); before = self.store.config_path.read_bytes()
        publish = delivery_lifecycle.commit_directory
        def replace_source(stage, final):
            result = publish(stage, final)
            replacement = self.root / 'edited-config.json'; replacement.write_bytes(before)
            replacement.replace(self.store.config_path)
            return result
        with patch.object(delivery_lifecycle, 'commit_directory', side_effect=replace_source):
            with self.assertRaisesRegex(ValueError, 'stale|differs|identity'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertFalse(self.store._path('relocations', plan['id'], 'switched').exists())
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_staged_payload_change_after_publish_is_preserved_and_refused(self):
        import delivery_lifecycle
        artifact, plan = self.prepared(); before = self.store.config_path.read_bytes()
        publish = delivery_lifecycle.commit_directory
        def edit_payload(stage, final):
            result = publish(stage, final)
            proof = self.store._read('relocations', plan['id'], 'configuration-prepared')
            Path(proof['staged_path']).write_bytes(b'changed')
            return result
        with patch.object(delivery_lifecycle, 'commit_directory', side_effect=edit_payload):
            with self.assertRaisesRegex(ValueError, 'changed|differs|identity'):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_git_policy_covers_configuration_evidence_for_an_actual_switch(self):
        import subprocess
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        artifact, plan = self.prepared_without_media_copy()
        policy = self.store.relocation_git_policy(plan['id'])
        self.assertIn('configuration_staging', policy)
        rules = self.root / '.gitignore'; rules.write_text('\n'.join(policy['gitignore']) + '\n')
        self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.assertEqual(json.loads(self.store.config_path.read_bytes())['storage'], self.targets())
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def prepared_without_media_copy(self):
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        return artifact, self.store.plan_relocation(self.targets())
