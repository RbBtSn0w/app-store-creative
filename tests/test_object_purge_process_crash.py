"""Ordinary purge recovers durable file checkpoints after actual process death."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
import test_retention_lifecycle as fixtures


class ObjectPurgeProcessCrashTests(unittest.TestCase):
    setUp = fixtures.RetentionTests.setUp
    artifact = fixtures.RetentionTests.artifact
    quarantined = fixtures.RetentionTests.quarantined

    def crash_case(self, stage):
        data, operation = self.quarantined()
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.store.config_path.write_text(json.dumps(self.cfg))
        scripts = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        code = """
import os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from artifact_lifecycle import Lifecycle
core = Lifecycle.from_configuration(Path(sys.argv[2]), Path(sys.argv[2])/'creative.config.json')
original = core._record
suffix = {'intent':'purge-intent', 'checkpoint':'purge-file-0', 'receipt':'purged'}[sys.argv[4]]
def record(category, body, name=None):
    if sys.argv[4]=='receipt' and category=='maintenance' and name==suffix:
        os.kill(os.getpid(), signal.SIGKILL)
    result = original(category, body, name)
    if sys.argv[4]!='receipt' and category=='maintenance' and name==suffix:
        os.kill(os.getpid(), signal.SIGKILL)
    return result
core._record = record
core.purge_cleanup(sys.argv[3], 'fixture-owner', 'Disposable process death drill')
"""
        killed = subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root), plan['id'], stage], capture_output=True, text=True, timeout=30)
        self.assertEqual(killed.returncode, -signal.SIGKILL, killed.stderr)
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'INCOMPLETE')
        resumed = subprocess.run([sys.executable, str(scripts/'app_store_creative.py'), 'cleanup', 'purge', '--repo', str(self.root), '--id', plan['id'], '--actor', 'fixture-owner', '--reason', 'Resume disposable drill', '--confirm', 'PURGE'], capture_output=True, text=True, timeout=30)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(json.loads(resumed.stdout)['status'], 'purged')
        self.assertEqual(self.store.maintenance_status(operation['id'])['status'], 'PASS')
        self.assertFalse(self.store._quarantine_path(operation['id'], data['sha256']).exists())
        self.assertTrue(self.store._path('artifacts', data['id']).exists())

    def test_intent_death_resumes_original_plan(self):
        self.crash_case('intent')

    def test_file_checkpoint_death_resumes_original_plan(self):
        self.crash_case('checkpoint')

    def test_terminal_receipt_death_resumes_original_plan(self):
        self.crash_case('receipt')
