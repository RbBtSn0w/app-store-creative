"""Studio maintenance plans and explicit reversible writes use the lifecycle core."""
import json
import unittest
import urllib.error
import test_incident_lifecycle as fixtures
import test_studio_release
import export_engine


class StudioMaintenanceTests(unittest.TestCase):
    setUp = fixtures.IncidentTests.setUp
    trial = fixtures.IncidentTests.trial
    request = test_studio_release.StudioReleaseTests.request

    def test_plan_quarantine_restore_and_restart_history(self):
        artifact, dependency = self.trial()
        self.store.config_path.write_text(json.dumps(self.cfg))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/maintenance/plan', {'retention_days': 0})
            self.assertEqual(len(plan['objects']), 2)
            operation, _ = self.request(ctx, '/api/maintenance/quarantine', {'id': plan['id'],
                'actor': 'test-owner', 'reason': 'Retire test trial', 'confirm': 'QUARANTINE'})
            self.assertFalse(self.store.object_path(artifact['sha256']).exists())
            restored, _ = self.request(ctx, '/api/maintenance/restore', {'id': operation['id'],
                'actor': 'test-owner', 'reason': 'Recover test trial', 'confirm': 'RESTORE'})
            self.assertEqual(restored['status'], 'restored')
            self.store.verify_artifact(artifact['id']); self.store.verify_artifact(dependency['id'])
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            history, _ = self.request(ctx, '/api/maintenance')
            saved = next(item for item in history['maintenance'] if item['id'] == operation['id'])
            self.assertEqual(saved['recorded_status'], 'restored')
            self.assertFalse(saved['execution_verified'])

    def test_missing_confirmation_and_stale_plan_never_quarantine(self):
        artifact, _ = self.trial()
        self.store.config_path.write_text(json.dumps(self.cfg))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/maintenance/plan', {'retention_days': 0})
            for payload in ({'id': plan['id'], 'actor': 'test-owner', 'reason': 'test'},
                            {'id': plan['id'], 'actor': 'test-owner', 'reason': 'test', 'confirm': 'PURGE'}):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/maintenance/quarantine', payload)
                self.assertEqual(failure.exception.code, 400); failure.exception.close()
            self.store.open_incident('test-owner', 'Protect current object', [artifact['id']])
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/maintenance/quarantine', {'id': plan['id'],
                    'actor': 'test-owner', 'reason': 'test', 'confirm': 'QUARANTINE'})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
        self.store.verify_artifact(artifact['id'])

    def test_purge_requires_separate_plan_retention_and_confirmation(self):
        artifact, _ = self.trial()
        self.store.config_path.write_text(json.dumps(self.cfg))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/maintenance/plan', {'retention_days': 0})
            operation, _ = self.request(ctx, '/api/maintenance/quarantine', {'id': plan['id'],
                'actor': 'test-owner', 'reason': 'Disposable fixture', 'confirm': 'QUARANTINE'})
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/maintenance/plan-purge', {'id': operation['id'], 'quarantine_days': 7})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            purge, _ = self.request(ctx, '/api/maintenance/plan-purge', {'id': operation['id'], 'quarantine_days': 0})
            payload = {'id': purge['id'], 'actor': 'test-owner', 'reason': 'Disposable fixture', 'confirm': 'QUARANTINE'}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/maintenance/purge', payload)
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            self.assertTrue(self.store._quarantine_path(operation['id'], artifact['sha256']).exists())
            payload['confirm'] = 'PURGE'
            result, _ = self.request(ctx, '/api/maintenance/purge', payload)
            self.assertEqual(result['status'], 'purged')
            self.assertFalse(self.store._quarantine_path(operation['id'], artifact['sha256']).exists())
            history, _ = self.request(ctx, '/api/maintenance')
            saved = next(item for item in history['maintenance'] if item['id'] == operation['id'])
            self.assertEqual(saved['recorded_status'], 'purged')
