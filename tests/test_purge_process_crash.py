"""Permanent purge checkpoints recover after real child process death."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
import test_relocation_purge_plan as fixtures


class PurgeProcessCrashTests(unittest.TestCase):
    setUp = fixtures.RelocationPurgePlanTests.setUp
    source = fixtures.RelocationPurgePlanTests.source
    targets = fixtures.RelocationPurgePlanTests.targets
    prepared = fixtures.RelocationPurgePlanTests.prepared
    moved = fixtures.RelocationPurgePlanTests.moved
    planned = fixtures.RelocationPurgePlanTests.planned
    staged = fixtures.RelocationPurgePlanTests.staged
    committed = fixtures.RelocationPurgePlanTests.committed

    def crash_case(self, stage):
        active, receipt, artifact = self.committed()
        plan = active.plan_relocation_purge(receipt['id'], quarantine_days=0)
        scripts = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        code = '''
import os,signal,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from artifact_lifecycle import Lifecycle
import purge_execution
core=Lifecycle.from_configuration(Path(sys.argv[2]),Path(sys.argv[2])/'creative.config.json')
def terminate():
    os.kill(os.getpid(),signal.SIGKILL)
if sys.argv[4]=='file':
    original=purge_execution._delete
    def delete(*arguments):
        original(*arguments)
        terminate()
    purge_execution._delete=delete
else:
    original=core._record
    expected='purge-intent' if sys.argv[4]=='intent' else 'purged'
    def record(category,data,suffix=None):
        if sys.argv[4]=='receipt' and category=='maintenance' and suffix==expected:
            terminate()
        result=original(category,data,suffix)
        if sys.argv[4]=='intent' and category=='maintenance' and suffix==expected:
            terminate()
        return result
    core._record=record
core.purge_relocation(sys.argv[3],'fixture-owner','Disposable process crash fixture')
'''
        result = subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root), plan['id'], stage],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
        active.verify_artifact(artifact['id'])
        row = next(item for item in active.inventory()['quarantine_preparations']['operations'] if item['id'] == receipt['id'])
        self.assertEqual(row['phase'], 'PURGING')
        self.assertEqual(len(row['files']), row['expected_file_count'])
        self.assertEqual(row['purge_plan'], plan)
        resumed = subprocess.run([sys.executable, str(scripts / 'app_store_creative.py'), 'cleanup', 'purge-relocation',
            '--repo', str(self.root), '--id', plan['id'], '--actor', 'fixture-owner', '--reason', 'Recover disposable purge fixture',
            '--confirm', 'PURGE'], capture_output=True, text=True, timeout=30)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(json.loads(resumed.stdout)['status'], 'PURGED')
        self.assertTrue(all(not Path(item['path']).exists() for item in plan['files']))
        self.assertTrue(all(Path(item['path']).exists() for item in plan['recovery']))
        active.verify_artifact(artifact['id'])

    def test_intent_process_death_resumes_public_purge(self):
        self.crash_case('intent')

    def test_file_checkpoint_process_death_resumes_public_purge(self):
        self.crash_case('file')

    def test_receipt_process_death_resumes_public_purge(self):
        self.crash_case('receipt')
