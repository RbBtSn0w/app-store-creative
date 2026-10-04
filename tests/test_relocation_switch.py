"""Relocation publishes inactive roots before atomically switching configuration."""
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import test_relocation_lifecycle as fixtures
from artifact_lifecycle import Lifecycle


class RelocationSwitchTests(unittest.TestCase):
    setUp = fixtures.RelocationTests.setUp
    source = fixtures.RelocationTests.source
    targets = fixtures.RelocationTests.targets

    def prepared(self):
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        plan = self.store.plan_relocation(self.targets())
        self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        return artifact, plan

    def test_switch_preserves_artifacts_and_old_records_and_fences_old_client(self):
        artifact, plan = self.prepared(); run = self.store._read('attempts', artifact['attempt_id'], 'started')['run_id']
        original = self.store._path('runs', run).read_bytes()
        result = self.store.switch_relocation(plan['id'], 'owner', 'Switch verified storage')
        self.assertEqual(result['status'], 'SWITCHED')
        config = json.loads(self.store.config_path.read_text()); moved = Lifecycle(self.root, config)
        moved.verify_artifact(artifact['id'])
        self.assertEqual(moved._path('runs', run).read_bytes(), original)
        moved._run(run)
        moved.start_run({})
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.start_run({})
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_interruption_after_directory_publish_keeps_target_inactive(self):
        artifact, plan = self.prepared()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Configuration write failed')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        cfg = {**self.cfg, 'storage': self.targets()}; moved = Lifecycle(self.root, cfg)
        with self.assertRaisesRegex(ValueError, 'inactive'):
            moved.start_run({})
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.start_run({})
        self.assertEqual(json.loads(self.store.config_path.read_text()), self.cfg)
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_changed_prepared_bytes_refuse_switch_before_fencing(self):
        self.source(); self.store.config_path.write_text(json.dumps(self.cfg))
        plan = self.store.plan_relocation(self.targets()); prepared = self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        Path(prepared['staged_files'][0]['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.switch_relocation(plan['id'], 'owner', 'Switch')
        self.store.start_run({})

    def test_object_only_move_keeps_workspace_and_supports_new_registration(self):
        artifact = self.source(); self.store.config_path.write_text(json.dumps(self.cfg))
        storage = {**self.cfg['storage'], 'objectRoot': 'moved objects'}
        plan = self.store.plan_relocation(storage); self.store.prepare_relocation(plan['id'], 'owner', 'Move objects')
        self.store.switch_relocation(plan['id'], 'owner', 'Switch objects')
        moved = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        self.assertEqual(moved.paths.workspace, self.store.paths.workspace)
        moved.verify_artifact(artifact['id'])
        run = moved.start_run({}); attempt = moved.start_attempt(run['id'], 'render', 'agent')
        source = moved.work_path(attempt['id']) / 'new'; source.write_bytes(b'new output')
        moved.register(attempt['id'], source, 'source')

    def test_actual_switch_preserves_approval_and_existing_archive(self):
        from test_delivery_lifecycle import DeliveryLifecycleTests
        fixture = DeliveryLifecycleTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        validation, approval = fixture.approved()
        delivery = fixture.store.seal(fixture.candidate['id'], validation['id'], approval['id'])
        fixture.store.config_path.write_text(json.dumps(fixture.config))
        plan = fixture.store.plan_relocation({'workspaceRoot': 'moved workspace',
            'releaseRoot': 'moved releases', 'publicationRoot': 'moved publications'})
        fixture.store.prepare_relocation(plan['id'], 'owner', 'Move')
        fixture.store.switch_relocation(plan['id'], 'owner', 'Switch')
        moved = Lifecycle(fixture.root, json.loads(fixture.store.config_path.read_text()))
        self.assertTrue(moved.delivery_path(delivery).is_dir())
        resealed = moved.seal(fixture.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(resealed['approval_id'], approval['id'])
