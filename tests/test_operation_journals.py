"""Unified journal reads preserve controls and do not infer successful execution."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_artifact_lifecycle as fixtures
import test_studio_release
import export_engine


class OperationJournalTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp
    request = test_studio_release.StudioReleaseTests.request

    def test_public_reads_match_core_and_preserve_all_record_bytes(self):
        plan = self.store.plan_cleanup(30)
        self.store.config_path.write_text(json.dumps(self.cfg))
        records = self.store.paths.workspace / 'records'
        before = {str(p):p.read_bytes() for p in records.rglob('*.json')}
        result = self.store.operation_journals()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertFalse(result['execution_verified'])
        self.assertEqual(result['entries'][0]['operation'], 'cleanup-plan')
        self.assertEqual(result['entries'][0]['id'], plan['id'])
        self.assertNotIn('storage', result['entries'][0])
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        executed = subprocess.run([sys.executable,str(cli),'history','operations','--repo',str(self.root)],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(executed.stdout),result)
        with export_engine.LocalServerContext(self.root,self.store.config_path) as ctx:
            remote,_=self.request(ctx,'/api/history/operations')
            self.assertEqual(remote,result)
        self.assertEqual(before,{str(p):p.read_bytes() for p in records.rglob('*.json')})

    def test_linked_journal_cannot_be_presented_as_operation_evidence(self):
        plan=self.store.plan_cleanup(30)
        path=self.store._path('maintenance',plan['id'])
        original=self.root/'outside.json';original.write_bytes(path.read_bytes())
        path.unlink();path.symlink_to(original)
        with self.assertRaisesRegex(ValueError,'link'):
            self.store.operation_journals()

    def test_public_journal_read_rejects_unknown_control_schemas_without_rewriting(self):
        from artifact_lifecycle import identifier
        from operation_history import JOURNAL_CATEGORIES
        self.store.start_run({})
        self.store.config_path.write_text(json.dumps(self.cfg))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        for category in sorted(JOURNAL_CATEGORIES):
            with self.store.transaction():
                record = self.store._record(category, {'id': identifier(), 'operation': 'schema-audit'})
            path = self.store._path(category, record['id'])
            for version in (None, True, 1.0, '1', 2):
                with self.subTest(category=category, version=version):
                    changed = {**record, 'schema_version': version}
                    if version is None:
                        changed.pop('schema_version')
                    path.write_text(json.dumps(changed))
                    before = path.read_bytes()
                    with self.assertRaisesRegex(ValueError, 'schema'):
                        self.store.operation_journals()
                    result = subprocess.run([sys.executable, str(cli), 'history', 'operations',
                                             '--repo', str(self.root)], capture_output=True, text=True,
                                            timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('schema', result.stderr + result.stdout)
                    self.assertEqual(path.read_bytes(), before)
            path.write_text(json.dumps(record))
