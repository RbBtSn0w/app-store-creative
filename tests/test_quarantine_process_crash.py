"""Real process death after source displacement recovers through public CLI."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
import test_relocation_quarantine_commit as fixtures


class QuarantineProcessCrashTests(unittest.TestCase):
    setUp = fixtures.RelocationQuarantineCommitTests.setUp
    source = fixtures.RelocationQuarantineCommitTests.source
    targets = fixtures.RelocationQuarantineCommitTests.targets
    prepared = fixtures.RelocationQuarantineCommitTests.prepared
    moved = fixtures.RelocationQuarantineCommitTests.moved
    planned = fixtures.RelocationQuarantineCommitTests.planned
    staged = fixtures.RelocationQuarantineCommitTests.staged

    def crash_case(self, restore, stage='move'):
        active, receipt, artifact = self.staged()
        if restore:
            active.commit_relocation_quarantine(receipt['id'], 'fixture-owner', 'Prepare restoration crash')
        scripts = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        code = '''
import os,signal,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from artifact_lifecycle import Lifecycle
import quarantine_commit
core=Lifecycle.from_configuration(Path(sys.argv[2]),Path(sys.argv[2])/'creative.config.json')
def terminate():
    os.kill(os.getpid(),signal.SIGKILL)
stage=sys.argv[5]
if stage=='move':
    original=quarantine_commit._move
    def move(*arguments):
        original(*arguments)
        terminate()
    quarantine_commit._move=move
elif stage=='intent':
    original=core._record
    expected='restore-intent' if sys.argv[4]=='restore' else 'commit-intent'
    def record(category,data,suffix=None):
        result=original(category,data,suffix)
        if category=='maintenance' and suffix==expected:
            terminate()
        return result
    core._record=record
elif stage=='receipt':
    original=core._record
    expected='restored' if sys.argv[4]=='restore' else 'quarantined'
    def record(category,data,suffix=None):
        if category=='maintenance' and suffix==expected:
            terminate()
        return original(category,data,suffix)
    core._record=record
method=core.restore_relocation_quarantine if sys.argv[4]=='restore' else core.commit_relocation_quarantine
method(sys.argv[3],'fixture-owner','Process crash acceptance')
'''
        result = subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root), receipt['id'],
            'restore' if restore else 'commit', stage], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
        phase = active.inventory()['quarantine_preparations']['operations'][0]['phase']
        self.assertEqual(phase, 'RESTORING' if restore else 'COMMIT_STARTED')
        action = 'restore-relocation-quarantine' if restore else 'commit-relocation-quarantine'
        resumed = subprocess.run([sys.executable, str(scripts / 'app_store_creative.py'), 'cleanup', action,
            '--repo', str(self.root), '--id', receipt['id'], '--actor', 'fixture-owner',
            '--reason', 'Recover process death', '--confirm', 'RESTORE' if restore else 'QUARANTINE'],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(json.loads(resumed.stdout)['status'], 'RESTORED' if restore else 'QUARANTINED')
        active.verify_artifact(artifact['id'])
        if not restore:
            active.restore_relocation_quarantine(receipt['id'], 'fixture-owner', 'Restore fixture')
        self.assertTrue(self.store.object_path(artifact['sha256']).exists())

    def test_commit_process_death_recovers_through_public_cli(self):
        self.crash_case(False)

    def test_restore_process_death_recovers_through_public_cli(self):
        self.crash_case(True)

    def test_commit_intent_process_death_recovers_through_public_cli(self):
        self.crash_case(False, 'intent')

    def test_restore_intent_process_death_recovers_through_public_cli(self):
        self.crash_case(True, 'intent')

    def test_commit_receipt_process_death_recovers_through_public_cli(self):
        self.crash_case(False, 'receipt')

    def test_restore_receipt_process_death_recovers_through_public_cli(self):
        self.crash_case(True, 'receipt')
