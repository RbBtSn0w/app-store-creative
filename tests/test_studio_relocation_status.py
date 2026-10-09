"""Studio exposes relocation evidence without creating or modifying records."""
import unittest
import urllib.error
import test_relocation_status as fixtures
import test_studio_release
import export_engine


class StudioRelocationStatusTests(unittest.TestCase):
    setUp = fixtures.RelocationStatusTests.setUp
    source = fixtures.RelocationStatusTests.source
    targets = fixtures.RelocationStatusTests.targets
    prepared = fixtures.RelocationStatusTests.prepared
    records = fixtures.RelocationStatusTests.records
    request = test_studio_release.StudioReleaseTests.request

    def test_object_inspection_matches_cli_after_restart_and_rejects_scope_overrides(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        from artifact_lifecycle import Lifecycle
        _, plan = self.prepared()
        self.store.switch_relocation(plan['id'], 'fixture-owner', 'Move disposable fixture')
        target = Lifecycle.from_configuration(self.root, self.store.config_path)
        target.start_run({})
        expected = target.relocated_object_status(plan['id'])
        before = {str(path): path.read_bytes() for path in target.paths.workspace.rglob('*.json')}
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        executed = subprocess.run([sys.executable, str(script), 'storage', 'inspect-relocated-objects', '--repo', str(self.root), '--id', plan['id']], capture_output=True, text=True, timeout=30)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(json.loads(executed.stdout), expected)
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            observed, _ = self.request(ctx, '/api/storage/relocated-objects?id=' + plan['id'])
            self.assertEqual(observed, expected)
            for query in ('id=' + plan['id'] + '&workspace=/tmp/override', 'id=' + plan['id'] + '&id=' + plan['id'], 'id='):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/storage/relocated-objects?' + query)
                self.assertEqual(failure.exception.code, 400); failure.exception.close()
        self.assertEqual(before, {str(path): path.read_bytes() for path in target.paths.workspace.rglob('*.json')})

    def test_http_reads_prepared_evidence_without_writes(self):
        _, plan = self.prepared()
        before = self.records()
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            result, _ = self.request(ctx, '/api/storage/relocation-status?id=' + plan['id'])
            self.assertEqual(result, self.store.relocation_status(plan['id']))
            for query in ('id=' + plan['id'] + '&workspace=/tmp/other', 'id=../other', 'id=' + plan['id'] + '&id=' + plan['id']):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(ctx, '/api/storage/relocation-status?' + query)
                self.assertEqual(failure.exception.code, 400)
                failure.exception.close()
        self.assertEqual(self.records(), before)

    def test_http_plan_verify_prepare_and_switch_require_exact_confirmation(self):
        import json
        from artifact_lifecycle import Lifecycle
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/storage/plan-relocate', {'storage': self.targets()})
            verified, _ = self.request(ctx, '/api/storage/verify-relocate', {'id': plan['id']})
            self.assertEqual(verified['status'], 'READY')
            payload = {'id': plan['id'], 'actor': 'test-owner', 'reason': 'Test relocation', 'confirm': 'SWITCH'}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/storage/prepare-relocate', payload)
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            payload['confirm'] = 'PREPARE'
            prepared, _ = self.request(ctx, '/api/storage/prepare-relocate', payload)
            self.assertEqual(prepared['status'], 'PREPARED')
            self.assertEqual(json.loads(self.store.config_path.read_text()), self.cfg)
            payload['confirm'] = 'SWITCH'
            switched, _ = self.request(ctx, '/api/storage/switch-relocate', payload)
            self.assertEqual(switched['status'], 'SWITCHED')
        moved = Lifecycle.from_configuration(self.root, self.store.config_path)
        moved.verify_artifact(artifact['id'])
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_http_interrupted_switch_recovers_from_explicit_source(self):
        from unittest.mock import patch
        _, plan = self.prepared()
        with patch('relocation_lifecycle.os.replace', side_effect=OSError('Interrupted configuration commit')):
            with self.assertRaises(OSError):
                self.store.switch_relocation(plan['id'], 'test-owner', 'Fixture switch')
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            payload = {'id': plan['id'], 'actor': 'test-owner', 'reason': 'Recover fixture',
                       'confirm': 'ROLLBACK', 'source_workspace': str(self.store.paths.workspace)}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/storage/rollback-relocate', {**payload, 'source_workspace': str(self.root / 'wrong-source')})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            result, _ = self.request(ctx, '/api/storage/rollback-relocate', payload)
            self.assertEqual(result['status'], 'ROLLED_BACK')
        self.store.start_run({})

    def test_http_reverse_plan_prepare_switch_preserves_new_artifact(self):
        from artifact_lifecycle import Lifecycle
        import json
        original, forward = self.prepared()
        self.store.switch_relocation(forward['id'], 'test-owner', 'Forward fixture')
        moved = Lifecycle.from_configuration(self.root, self.store.config_path)
        run = moved.start_run({})
        attempt = moved.start_attempt(run['id'], 'fixture', 'test-owner')
        source = __import__('pathlib').Path(attempt['work_path']) / 'new.bin'
        source.write_bytes(b'New artifact after forward switch')
        new = moved.register(attempt['id'], source, 'source')
        moved.finish_attempt(attempt['id'], 'succeeded')
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            plan, _ = self.request(ctx, '/api/storage/plan-reverse-relocate', {'id': forward['id']})
            self.assertEqual(plan['operation'], 'reverse-relocation-plan')
            verified, _ = self.request(ctx, '/api/storage/verify-reverse-relocate', {'id': plan['id']})
            self.assertEqual(verified['status'], 'READY')
            payload = {'id': plan['id'], 'actor': 'test-owner', 'reason': 'Return fixture', 'confirm': 'PREPARE'}
            prepared, _ = self.request(ctx, '/api/storage/prepare-reverse-relocate', payload)
            self.assertEqual(prepared['status'], 'PREPARED')
            payload['confirm'] = 'SWITCH'
            result, _ = self.request(ctx, '/api/storage/switch-reverse-relocate', payload)
            self.assertEqual(result['status'], 'SWITCHED')
        returned = Lifecycle.from_configuration(self.root, self.store.config_path)
        returned.verify_artifact(original['id']); returned.verify_artifact(new['id'])
        self.assertEqual(returned.paths.binding(), self.store.paths.binding())
