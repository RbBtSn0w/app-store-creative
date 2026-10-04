"""Independent writers encounter source locks and pending target activation."""
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import unittest
import test_relocation_switch as fixtures


class RelocationConcurrencyTests(unittest.TestCase):
    setUp = fixtures.RelocationSwitchTests.setUp
    source = fixtures.RelocationSwitchTests.source
    targets = fixtures.RelocationSwitchTests.targets
    prepared = fixtures.RelocationSwitchTests.prepared

    def test_independent_source_and_target_writers_cannot_cross_switch_boundary(self):
        _, plan = self.prepared()
        runtime = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        script = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
                  'from artifact_lifecycle import Lifecycle;'
                  'print("ready",flush=True);'
                  'Lifecycle(sys.argv[2],json.loads(sys.argv[3]),sys.argv[4]).start_run({})')
        def command(cfg):
            return [sys.executable, '-c', script, str(runtime), str(self.root),
                    json.dumps(cfg), str(self.store.config_path)]
        import os
        replace = os.replace; source_processes = []; target_results = []
        def at_configuration_commit(source, destination):
            pending = {**self.cfg, 'storage': self.targets()}
            target = subprocess.run(command(pending), capture_output=True, text=True, timeout=10)
            target_results.append(target)
            source_process = subprocess.Popen(command(self.cfg), stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, text=True)
            source_processes.append(source_process)
            self.assertEqual(source_process.stdout.readline().strip(), 'ready')
            self.assertIsNone(source_process.poll())
            return replace(source, destination)
        try:
            with patch('relocation_lifecycle.os.replace', side_effect=at_configuration_commit):
                self.store.switch_relocation(plan['id'], 'owner', 'Switch under concurrent clients')
            self.assertEqual(len(target_results), 1)
            self.assertNotEqual(target_results[0].returncode, 0)
            self.assertIn('inactive', target_results[0].stderr)
            for process in source_processes:
                _, stderr = process.communicate(timeout=10)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn('fenced', stderr)
        finally:
            for process in source_processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def test_unpublished_target_binding_cannot_create_workspace(self):
        from artifact_lifecycle import Lifecycle
        _, plan = self.prepared()
        target = Lifecycle(self.root, {**self.cfg, 'storage': self.targets()}, self.store.config_path)
        with self.assertRaisesRegex(ValueError, 'configuration storage'):
            target.start_run({})
        self.assertFalse(target.paths.workspace.exists())
