"""Public recovery survives process death after configuration installation."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
import test_reverse_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class RelocationProcessCrashTests(unittest.TestCase):
    setUp = fixtures.ReverseRelocationSwitchTests.setUp
    source = fixtures.ReverseRelocationSwitchTests.source
    targets = fixtures.ReverseRelocationSwitchTests.targets
    prepared = fixtures.ReverseRelocationSwitchTests.prepared
    moved = fixtures.ReverseRelocationSwitchTests.moved
    reverse = fixtures.ReverseRelocationSwitchTests.reverse

    def crash(self, core, plan, reverse=False, stage="configuration"):
        scripts = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        code = '''
import json, os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from artifact_lifecycle import Lifecycle
root = Path(sys.argv[2])
core = Lifecycle(root, json.loads((root / 'creative.config.json').read_text()))
def terminate(*arguments):
    os.kill(os.getpid(), signal.SIGKILL)
stage = sys.argv[5]
if stage == 'configuration':
    core._sync_configuration_directory = terminate
elif stage == 'intent':
    original = core._record
    def record(category, data, suffix=None):
        result = original(category, data, suffix)
        if category == 'relocations' and suffix == 'switch-intent':
            terminate()
        return result
    core._record = record
elif stage == 'directory':
    if sys.argv[4] == 'reverse':
        import delivery_lifecycle
        original = delivery_lifecycle.apply_directory_change
        def publish(change):
            result = original(change)
            terminate()
            return result
        delivery_lifecycle.apply_directory_change = publish
    else:
        import delivery_lifecycle
        original = delivery_lifecycle.commit_directory
        def publish(*arguments):
            result = original(*arguments)
            terminate()
            return result
        delivery_lifecycle.commit_directory = publish
elif stage == 'receipt':
    original = core._write_path
    def write(path, data):
        if Path(path).name == 'switched.json' and Path(path).parent.name == sys.argv[3]:
            terminate()
        return original(path, data)
    core._write_path = write
operation = core.switch_reverse_relocation if sys.argv[4] == 'reverse' else core.switch_relocation
operation(sys.argv[3], 'test-owner', 'Process crash acceptance')
'''
        result = subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root), plan['id'],
                                 'reverse' if reverse else 'forward', stage], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
        if stage in ('configuration', 'receipt'):
            self.assertNotEqual(json.loads(core.config_path.read_text()), core.config)

    def recover(self, core, plan, action, reverse=False, expected_success=True):
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = action + ('-reverse-relocate' if reverse else '-relocate')
        result = subprocess.run([sys.executable, str(cli), 'storage', command, '--repo', str(self.root),
            '--source-workspace', str(core.paths.workspace), '--id', plan['id'], '--actor', 'test-owner',
            '--reason', 'Recover process crash', '--confirm', action.upper()], capture_output=True, text=True, timeout=30)
        if not expected_success:
            self.assertNotEqual(result.returncode, 0)
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def forward_case(self, action, stage="configuration"):
        artifact, plan = self.prepared()
        before = self.store.config_path.read_bytes()
        self.crash(self.store, plan, stage=stage)
        result = self.recover(self.store, plan, action)
        self.assertEqual(result['status'], 'SWITCHED' if action == 'resume' else 'ROLLED_BACK')
        active = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        active.verify_artifact(artifact['id']); active.start_run({})
        self.assertEqual(active.paths.binding(), plan['to'] if action == 'resume' else plan['from'])
        if action == 'rollback':
            self.assertEqual(self.store.config_path.read_bytes(), before)

    def reverse_case(self, action, stage="configuration"):
        artifact, forward, moved, plan, run = self.reverse()
        before = moved.config_path.read_bytes()
        self.crash(moved, plan, True, stage)
        result = self.recover(moved, plan, action, True)
        self.assertEqual(result['status'], 'SWITCHED' if action == 'resume' else 'ROLLED_BACK')
        active = Lifecycle(self.root, json.loads(moved.config_path.read_text()))
        active.verify_artifact(artifact['id']); active._run(run['id']); active.start_run({})
        self.assertEqual(active.paths.binding(), plan['to'] if action == 'resume' else plan['from'])
        if action == 'rollback':
            self.assertEqual(moved.config_path.read_bytes(), before)

    def test_forward_process_death_resumes_through_public_cli(self):
        self.forward_case('resume')

    def test_forward_process_death_rolls_back_through_public_cli(self):
        self.forward_case('rollback')

    def test_reverse_process_death_resumes_through_public_cli(self):
        self.reverse_case('resume')

    def test_reverse_process_death_rolls_back_through_public_cli(self):
        self.reverse_case('rollback')


    def test_missing_fence_reconstruction_refuses_changed_source(self):
        artifact, plan = self.prepared()
        self.crash(self.store, plan, stage='intent')
        before = self.store.config_path.read_bytes()
        self.store.object_path(artifact['sha256']).write_bytes(b'changed after process death')
        self.recover(self.store, plan, 'resume', expected_success=False)
        self.assertEqual(self.store.config_path.read_bytes(), before)
        self.assertEqual(list((self.store.paths.workspace / 'records/storage-fences').glob('*/*.json')), [])


def matrix_test(direction, action, stage):
    def test(self):
        operation = self.reverse_case if direction == 'reverse' else self.forward_case
        operation(action, stage)
    return test


for direction in ('forward', 'reverse'):
    for action in ('resume', 'rollback'):
        for stage in ('intent', 'directory', 'receipt'):
            setattr(RelocationProcessCrashTests, f'test_{direction}_{stage}_process_death_{action}',
                    matrix_test(direction, action, stage))
