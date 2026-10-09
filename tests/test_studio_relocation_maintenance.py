"""Studio relocation maintenance delegates reversible operations to the core."""
import unittest
import urllib.error
import export_engine
import test_relocation_retention_plan as fixtures
import test_studio_release


class StudioRelocationMaintenanceTests(unittest.TestCase):
    setUp = fixtures.RelocationRetentionPlanTests.setUp
    source = fixtures.RelocationRetentionPlanTests.source
    targets = fixtures.RelocationRetentionPlanTests.targets
    prepared = fixtures.RelocationRetentionPlanTests.prepared
    moved = fixtures.RelocationRetentionPlanTests.moved
    request = test_studio_release.StudioReleaseTests.request

    def test_http_plan_prepare_commit_restore_preserves_active_objects(self):
        active, _, artifact = self.moved()
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/relocation-maintenance/plan', {'retention_days': 0})
            self.assertTrue(any(item['decision'] == 'eligible' for item in plan['files']))
            payload = {'id': plan['id'], 'actor': 'fixture-owner', 'reason': 'Retire redundant fixture', 'confirm': 'PREPARE'}
            prepared, _ = self.request(ctx, '/api/relocation-maintenance/prepare', payload)
            observed, _ = self.request(ctx, '/api/relocation-maintenance')
            row = next(item for item in observed['operations'] if item['id'] == prepared['id'])
            self.assertEqual(row['phase'], 'PREPARED')
            self.assertEqual(row['files'][0]['sha256'], artifact['sha256'])
            self.assertEqual(row['files'][0]['path'], str(self.store.object_path(artifact['sha256'])))
            self.assertFalse(observed['cleanup_executed'])
            payload['id'] = prepared['id']; payload['confirm'] = 'COMMIT'
            committed, _ = self.request(ctx, '/api/relocation-maintenance/commit', payload)
            self.assertEqual(committed['status'], 'QUARANTINED')
            self.assertFalse(self.store.object_path(artifact['sha256']).exists())
            active.verify_artifact(artifact['id'])
            payload['confirm'] = 'RESTORE'
            restored, _ = self.request(ctx, '/api/relocation-maintenance/restore', payload)
            self.assertEqual(restored['status'], 'RESTORED')
            self.assertTrue(self.store.object_path(artifact['sha256']).exists())


    def test_invalid_requests_cannot_prepare_or_remove_source(self):
        active, _, artifact = self.moved()
        source = self.store.object_path(artifact['sha256'])
        before = source.read_bytes()
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/relocation-maintenance/plan', {'retention_days': 0})
            valid = {'id': plan['id'], 'actor': 'fixture-owner', 'reason': 'Fixture', 'confirm': 'PREPARE'}
            requests = [
                ('prepare', {**valid, 'confirm': 'COMMIT'}),
                ('prepare', {**valid, 'actor': ' '}),
                ('prepare', {**valid, 'workspace': '/tmp/override'}),
                ('prepare?workspace=/tmp/override', valid),
                ('plan', {'retention_days': True}),
                ('plan', {'retention_days': -1}),
                ('unknown', valid),
            ]
            for action, payload in requests:
                with self.subTest(action=action, payload=payload):
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        self.request(ctx, '/api/relocation-maintenance/' + action, payload)
                    self.assertEqual(failure.exception.code, 400)
                    failure.exception.close()
                    self.assertEqual(source.read_bytes(), before)
                    active.verify_artifact(artifact['id'])
            verified, _ = self.request(ctx, '/api/relocation-maintenance/verify', {'id': plan['id']})
            self.assertIsInstance(verified, dict)


    def test_resume_and_cancel_preparation_keep_original_copies(self):
        from pathlib import Path
        active, _, artifact = self.moved()
        source = self.store.object_path(artifact['sha256'])
        before = source.read_bytes()
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/relocation-maintenance/plan', {'retention_days': 0})
            payload = {'id': plan['id'], 'actor': 'fixture-owner', 'reason': 'Disposable fixture', 'confirm': 'PREPARE'}
            prepared, _ = self.request(ctx, '/api/relocation-maintenance/prepare', payload)
            recovery = Path(prepared['copies'][0]['quarantine_path'])
            inode = recovery.stat().st_ino
            payload['id'] = prepared['id']; payload['confirm'] = 'RESUME'
            resumed, _ = self.request(ctx, '/api/relocation-maintenance/resume', payload)
            self.assertEqual(resumed, prepared)
            self.assertEqual(recovery.stat().st_ino, inode)
            payload['confirm'] = 'CANCEL'
            cancelled, _ = self.request(ctx, '/api/relocation-maintenance/cancel', payload)
            self.assertEqual(cancelled['status'], 'CANCELLED')
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(recovery.stat().st_ino, inode)
            active.verify_artifact(artifact['id'])
            observed, _ = self.request(ctx, '/api/relocation-maintenance')
            row = next(item for item in observed['operations'] if item['id'] == prepared['id'])
            self.assertEqual(row['phase'], 'CANCELLED')
            self.assertFalse(row['source_removal_executed'])
            payload['confirm'] = 'COMMIT'
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/relocation-maintenance/commit', payload)
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()
            self.assertEqual(source.read_bytes(), before)


    def test_partial_copy_interruption_is_observed_and_never_overwritten(self):
        from pathlib import Path
        from unittest.mock import patch
        active, _, artifact = self.moved()
        source = self.store.object_path(artifact['sha256'])
        before = source.read_bytes()
        def partial(source_stream, target_stream):
            target_stream.write(b'partial-fixture'); target_stream.flush()
            raise OSError('Injected partial copy interruption')
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/relocation-maintenance/plan', {'retention_days': 0})
            payload = {'id': plan['id'], 'actor': 'fixture-owner', 'reason': 'Recovery fixture', 'confirm': 'PREPARE'}
            with patch('relocation_quarantine.shutil.copyfileobj', side_effect=partial):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/relocation-maintenance/prepare', payload)
                self.assertEqual(failure.exception.code, 500); failure.exception.close()
            observed, _ = self.request(ctx, '/api/relocation-maintenance')
            row = observed['operations'][0]
            self.assertEqual(row['phase'], 'INTERRUPTED')
            self.assertEqual(row['status'], 'PARTIAL')
            retained = next(Path(row['path']).iterdir())
            self.assertEqual(retained.read_bytes(), b'partial-fixture')
            payload['id'] = row['id']; payload['confirm'] = 'RESUME'
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/relocation-maintenance/resume', payload)
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            self.assertEqual(retained.read_bytes(), b'partial-fixture')
            payload['confirm'] = 'CANCEL'
            cancelled, _ = self.request(ctx, '/api/relocation-maintenance/cancel', payload)
            self.assertEqual(cancelled['status'], 'CANCELLED')
            self.assertEqual(source.read_bytes(), before)
            active.verify_artifact(artifact['id'])


    def test_purge_requires_retention_confirmation_and_preserves_active_recovery(self):
        from pathlib import Path
        active, _, artifact = self.moved()
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/relocation-maintenance/plan', {'retention_days': 0})
            payload = {'id': plan['id'], 'actor': 'fixture-owner', 'reason': 'Plan-only fixture', 'confirm': 'PREPARE'}
            prepared, _ = self.request(ctx, '/api/relocation-maintenance/prepare', payload)
            payload['id'] = prepared['id']; payload['confirm'] = 'COMMIT'
            self.request(ctx, '/api/relocation-maintenance/commit', payload)
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/relocation-maintenance/plan-purge', {'id': prepared['id'], 'quarantine_days': 7})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            purge, _ = self.request(ctx, '/api/relocation-maintenance/plan-purge', {'id': prepared['id'], 'quarantine_days': 0})
            self.assertEqual(purge['operation'], 'relocation-purge-plan')
            self.assertFalse(purge['purge_executed'])
            self.assertEqual(len(purge['files']), 2)
            for item in purge['files']:
                self.assertTrue(Path(item['path']).exists())
            verified, _ = self.request(ctx, '/api/relocation-maintenance/verify-purge', {'id': purge['id']})
            self.assertEqual(verified['status'], 'READY')
            deletion = {'id': purge['id'], 'actor': 'fixture-owner', 'reason': 'Delete disposable fixture copies', 'confirm': 'COMMIT'}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/relocation-maintenance/purge', deletion)
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            self.assertTrue(all(Path(item['path']).exists() for item in purge['files']))
            deletion['confirm'] = 'PURGE'
            result, _ = self.request(ctx, '/api/relocation-maintenance/purge', deletion)
            self.assertEqual(result['status'], 'PURGED')
            self.assertTrue(all(not Path(item['path']).exists() for item in purge['files']))
            self.assertTrue(all(Path(item['path']).exists() for item in purge['recovery']))
            observed, _ = self.request(ctx, '/api/relocation-maintenance')
            row = next(item for item in observed['operations'] if item['id'] == prepared['id'])
            self.assertEqual(row['phase'], 'PURGED')
            self.assertEqual(row['status'], 'PURGED')
            self.assertEqual(len(row['files']), row['expected_file_count'])
            self.assertEqual(row['purge_plan'], purge)
            active.verify_artifact(artifact['id'])


    def test_interrupted_purge_reloads_exact_plan_and_resumes_after_server_restart(self):
        from pathlib import Path
        from unittest.mock import patch
        import purge_execution
        active, _, artifact = self.moved()
        plan = active.plan_relocation_retention(retention_days=0)
        prepared = active.prepare_relocation_quarantine(plan['id'], 'fixture-owner', 'Disposable restart fixture')
        active.commit_relocation_quarantine(prepared['id'], 'fixture-owner', 'Disposable restart fixture')
        purge = active.plan_relocation_purge(prepared['id'], quarantine_days=0)
        original = purge_execution._delete
        def interrupted(*arguments):
            original(*arguments)
            raise OSError('Injected interruption after one durable deletion')
        deletion = {'id': purge['id'], 'actor': 'fixture-owner', 'reason': 'Disposable restart fixture', 'confirm': 'PURGE'}
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            with patch('purge_execution._delete', side_effect=interrupted):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/relocation-maintenance/purge', deletion)
                self.assertEqual(failure.exception.code, 500); failure.exception.close()
        with export_engine.LocalServerContext(self.root, active.config_path) as ctx:
            observed, _ = self.request(ctx, '/api/relocation-maintenance')
            row = next(item for item in observed['operations'] if item['id'] == prepared['id'])
            self.assertEqual(row['phase'], 'PURGING')
            self.assertEqual(row['purge_plan'], purge)
            self.assertEqual(len(row['files']), row['expected_file_count'])
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/relocation-maintenance/plan-purge', {'id': prepared['id'], 'quarantine_days': 0})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            resumed, _ = self.request(ctx, '/api/relocation-maintenance/purge', deletion)
            self.assertEqual(resumed['status'], 'PURGED')
        self.assertTrue(all(not Path(item['path']).exists() for item in purge['files']))
        self.assertTrue(all(Path(item['path']).exists() for item in purge['recovery']))
        active.verify_artifact(artifact['id'])


if __name__ == '__main__':
    unittest.main()
