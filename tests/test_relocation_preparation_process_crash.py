"""Copy preparation recovery preserves interrupted batches after process death."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
import test_relocation_switch as fixtures
from artifact_lifecycle import Lifecycle


class PreparationProcessCrashTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets

    def case(self, stage):
        artifact = self.source()
        self.store.config_path.write_text(json.dumps(self.cfg))
        plan = self.store.plan_relocation(self.targets())
        scripts = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        code = '''
import json, os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from artifact_lifecycle import Lifecycle
root = Path(sys.argv[2])
core = Lifecycle(root, json.loads((root / 'creative.config.json').read_text()))
def terminate():
    os.kill(os.getpid(), signal.SIGKILL)
if sys.argv[4] == 'intent':
    original = core._record
    def record(category, data, suffix=None):
        result = original(category, data, suffix)
        if suffix == 'prepare-intent':
            terminate()
        return result
    core._record = record
else:
    import relocation_lifecycle
    original = relocation_lifecycle.shutil.copyfileobj
    def copy(source, destination):
        original(source, destination)
        destination.flush()
        terminate()
    relocation_lifecycle.shutil.copyfileobj = copy
core.prepare_relocation(sys.argv[3], 'test-owner', 'Process crash acceptance')
'''
        result = subprocess.run([sys.executable, '-c', code, str(scripts), str(self.root), plan['id'], stage],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
        intent = self.store._read('relocations', plan['id'], 'prepare-intent')
        surviving = {path: path.read_bytes() for root in intent['staging'].values()
                     for path in Path(root).rglob('*') if path.is_file()}
        cli = scripts / 'app_store_creative.py'
        def call(action, identity, confirmation):
            result = subprocess.run([sys.executable, str(cli), 'storage', action, '--repo', str(self.root),
                '--id', identity, '--actor', 'test-owner', '--reason', 'Recover interrupted copy',
                '--confirm', confirmation], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        recovery = call('recover-relocate', plan['id'], 'RECOVER')
        self.assertNotEqual(recovery['retry_plan_id'], plan['id'])
        prepared = call('prepare-relocate', recovery['retry_plan_id'], 'PREPARE')
        self.assertEqual(prepared['status'], 'PREPARED')
        for path, data in surviving.items():
            self.assertEqual(path.read_bytes(), data)
        call('switch-relocate', recovery['retry_plan_id'], 'SWITCH')
        active = Lifecycle(self.root, json.loads(self.store.config_path.read_text()))
        active.verify_artifact(artifact['id']); active.start_run({})
        self.assertEqual(active.paths.binding(), plan['to'])

    def test_prepare_intent_process_death_recovers_to_new_batch(self):
        self.case('intent')

    def test_first_copy_process_death_preserves_original_partial_batch(self):
        self.case('copy')
