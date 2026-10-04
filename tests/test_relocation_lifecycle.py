"""Relocation plans bind exact bytes and refuse unsafe or active moves."""
from pathlib import Path
import unittest
import test_artifact_lifecycle as fixtures


class RelocationTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def source(self, finish=True):
        run = self.store.start_run({}); attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.store.work_path(attempt['id']) / 'source'; source.write_bytes(b'snapshot')
        artifact = self.store.register(attempt['id'], source, 'source')
        if finish:
            self.store.finish_attempt(attempt['id'], 'failed', reason='Unused trial')
        return artifact

    def targets(self):
        return {'workspaceRoot': 'new work', 'objectRoot': 'new objects',
                'releaseRoot': 'new deliveries', 'publicationRoot': 'new publications'}

    def test_plan_binds_source_hashes_without_creating_destinations(self):
        artifact = self.source()
        plan = self.store.plan_relocation(self.targets())
        self.assertEqual(plan['from'], self.store.paths.binding())
        self.assertEqual(plan['to']['workspace'], str(self.root / 'new work'))
        self.assertTrue(any(item['sha256'] == artifact['sha256'] for item in plan['files']))
        self.assertFalse(plan['relocation_executed'])
        for path in plan['to'].values():
            self.assertFalse(Path(path).exists())
        self.assertEqual(self.store.verify_relocation_plan(plan['id'])['status'], 'READY')

    def test_active_attempt_blocks_relocation(self):
        self.source(finish=False)
        with self.assertRaisesRegex(ValueError, 'active'):
            self.store.plan_relocation(self.targets())

    def test_existing_destination_and_source_overlap_are_rejected(self):
        self.source()
        (self.root / 'new work').mkdir()
        with self.assertRaisesRegex(ValueError, 'exists'):
            self.store.plan_relocation(self.targets())
        with self.assertRaisesRegex(ValueError, 'source|overlap'):
            self.store.plan_relocation({**self.targets(), 'workspaceRoot': 'working area/nested'})

    def test_changed_bytes_make_existing_plan_stale(self):
        artifact = self.source()
        plan = self.store.plan_relocation(self.targets())
        source = self.store.paths.workspace / artifact['workspace_path']
        source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.store.verify_relocation_plan(plan['id'])

    def test_unknown_symlink_is_not_copied_or_followed(self):
        self.source()
        (self.store.paths.workspace / 'unknown-link').symlink_to(self.root / 'private')
        with self.assertRaisesRegex(ValueError, 'symlink|links'):
            self.store.plan_relocation(self.targets())

    def test_noop_relocation_is_rejected(self):
        self.source()
        with self.assertRaisesRegex(ValueError, 'unchanged'):
            self.store.plan_relocation(self.cfg['storage'])

    def test_nested_objects_are_listed_once_and_follow_new_workspace_default(self):
        import artifact_lifecycle
        self.cfg = {'project': {'id': 'demo'}, 'storage': {'workspaceRoot': 'nested work',
            'releaseRoot': 'nested deliveries', 'publicationRoot': 'nested publications'}}
        self.store = artifact_lifecycle.Lifecycle(self.root, self.cfg)
        self.source()
        plan = self.store.plan_relocation({'workspaceRoot': 'moved work',
            'releaseRoot': 'moved deliveries', 'publicationRoot': 'moved publications'})
        self.assertEqual(plan['to']['objects'], str(self.root / 'moved work/objects'))
        self.assertFalse(any(item['root'] == 'workspace' and item['path'].startswith('objects/') for item in plan['files']))
        self.assertTrue(any(item['root'] == 'objects' for item in plan['files']))

    def test_configuration_change_invalidates_plan(self):
        import json
        self.source()
        config = self.root / 'creative.config.json'; config.write_text(json.dumps(self.cfg))
        plan = self.store.plan_relocation(self.targets())
        config.write_text(json.dumps({**self.cfg, 'description': 'Changed during review'}))
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.store.verify_relocation_plan(plan['id'])

    def test_cli_plan_and_verify_use_same_core(self):
        import json
        import subprocess
        import sys
        self.source()
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        (self.root / 'storage-target.json').write_text(json.dumps(self.targets()))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = [sys.executable, str(cli), 'storage']
        planned = subprocess.run(command + ['plan-relocate', '--repo', str(self.root), '--storage', 'storage-target.json'], capture_output=True, text=True)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        identity = json.loads(planned.stdout)['id']
        verified = subprocess.run(command + ['verify-relocate', '--repo', str(self.root), '--id', identity], capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout)['status'], 'READY')
        self.assertFalse((self.root / 'new work').exists())

    def test_prepare_copies_verified_bytes_without_switching_or_deleting_source(self):
        artifact = self.source()
        plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move local workspace')
        self.assertEqual(prepared['status'], 'PREPARED')
        for item in prepared['staged_files']:
            from artifact_lifecycle import digest
            path = Path(item['path'])
            self.assertEqual(digest(path), item['sha256'])
        self.store.verify_artifact(artifact['id'])
        for path in plan['to'].values():
            self.assertFalse(Path(path).exists())
        self.assertEqual(self.store.prepare_relocation(plan['id'], actor='owner', reason='Retry')['id'], prepared['id'])

    def test_prepare_rejects_stale_plan_before_creating_staging(self):
        artifact = self.source()
        plan = self.store.plan_relocation(self.targets())
        (self.store.paths.workspace / artifact['workspace_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        self.assertEqual(list(self.root.glob('.creative-relocate-*')), [])

    def test_prepared_tampering_is_rejected_without_affecting_source(self):
        artifact = self.source(); plan = self.store.plan_relocation(self.targets())
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        Path(prepared['staged_files'][-1]['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.prepare_relocation(plan['id'], actor='owner', reason='Retry')
        self.store.verify_artifact(artifact['id'])

    def test_copy_failure_records_failure_and_preserves_source(self):
        from unittest.mock import patch
        artifact = self.source(); plan = self.store.plan_relocation(self.targets())
        with patch('relocation_lifecycle.shutil.copyfileobj', side_effect=OSError('Disk unavailable')):
            with self.assertRaisesRegex(OSError, 'Disk unavailable'):
                self.store.prepare_relocation(plan['id'], actor='owner', reason='Move')
        self.assertEqual(self.store._read('relocations', plan['id'], 'prepare-outcome')['status'], 'PREPARATION_FAILED')
        self.store.verify_artifact(artifact['id'])
        self.assertFalse((self.root / 'new work').exists())

    def test_object_only_prepare_inside_retained_workspace(self):
        import artifact_lifecycle
        self.cfg = {'project': {'id': 'demo'}, 'storage': {'workspaceRoot': 'nested work',
            'releaseRoot': 'nested deliveries', 'publicationRoot': 'nested publications'}}
        self.store = artifact_lifecycle.Lifecycle(self.root, self.cfg)
        self.source()
        plan = self.store.plan_relocation({**self.cfg['storage'], 'objectRoot': 'nested work/newobjects'})
        prepared = self.store.prepare_relocation(plan['id'], actor='owner', reason='Move objects')
        self.assertEqual(set(prepared['staging']), {'objects'})
        self.assertFalse((self.root / 'nested work/newobjects').exists())
