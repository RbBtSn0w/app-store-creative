"""Local migration returns through the same public reverse lifecycle."""
import unittest
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import test_configuration_local_forward_execution as fixtures
from relocation_lifecycle import recovery_source
from artifact_lifecycle import Lifecycle


class LocalReverseExecutionTests(unittest.TestCase):
    setUp = fixtures.LocalForwardExecutionTests.setUp
    write_local = fixtures.LocalForwardExecutionTests.write_local
    git = fixtures.LocalForwardExecutionTests.git
    prepared = fixtures.LocalForwardExecutionTests.prepared

    def cycle(self, cli=False):
        shared = self.path.read_bytes(); core, forward, artifact = self.prepared()
        core.switch_relocation(forward['id'], 'fixture', 'Forward')
        current_id = forward['id']
        for expected in ('host work', 'next host', 'host work'):
            core = Lifecycle.from_configuration(self.root, self.path)
            plan = core.plan_reverse_relocation(current_id)
            if cli:
                policy = core.relocation_git_policy(plan['id'])
                rules = self.root/'.gitignore'
                rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
            core.prepare_reverse_relocation(plan['id'], 'fixture', 'Prepare reverse')
            if cli:
                script = Path(__file__).parents[1]/'plugins/app-store-creative/scripts/app_store_creative.py'
                result = subprocess.run([sys.executable, str(script), 'storage', 'switch-reverse-relocate',
                    '--id', plan['id'], '--actor', 'fixture', '--reason', 'Verified reverse',
                    '--confirm', 'SWITCH', '--repo', str(self.root)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'SWITCHED')
            else:
                core.switch_reverse_relocation(plan['id'], 'fixture', 'Switch reverse')
            moved = Lifecycle.from_configuration(self.root, self.path)
            self.assertEqual(moved.paths.workspace, self.root/expected)
            moved.verify_artifact(artifact['id']); moved.start_run({})
            self.assertEqual(self.path.read_bytes(), shared)
            current_id = plan['id']

    def reverse_prepared(self):
        core, forward, artifact = self.prepared()
        core.switch_relocation(forward['id'], 'fixture', 'Forward')
        moved = Lifecycle.from_configuration(self.root, self.path)
        plan = moved.plan_reverse_relocation(forward['id'])
        moved.prepare_reverse_relocation(plan['id'], 'fixture', 'Prepare reverse')
        return moved, plan, artifact

    def test_local_reverse_post_install_resume(self):
        moved, plan, artifact = self.reverse_prepared(); shared = self.path.read_bytes()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(plan['id'], 'fixture', 'Reverse')
        source = recovery_source(self.root, self.path, moved.paths.workspace, plan['id'])
        source.resume_reverse_relocation(plan['id'], 'fixture', 'Resume reverse')
        active = Lifecycle.from_configuration(self.root, self.path)
        self.assertEqual(active.paths.workspace, self.root/'host work')
        active.verify_artifact(artifact['id']); self.assertEqual(self.path.read_bytes(), shared)

    def test_local_reverse_post_install_rollback(self):
        moved, plan, artifact = self.reverse_prepared(); local = self.local.read_bytes(); shared = self.path.read_bytes()
        with patch.object(moved, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError): moved.switch_reverse_relocation(plan['id'], 'fixture', 'Reverse')
        source = recovery_source(self.root, self.path, moved.paths.workspace, plan['id'])
        source.rollback_reverse_relocation(plan['id'], 'fixture', 'Rollback reverse')
        active = Lifecycle.from_configuration(self.root, self.path)
        self.assertEqual(active.paths.workspace, self.root/'next host')
        active.verify_artifact(artifact['id'])
        self.assertEqual(self.local.read_bytes(), local); self.assertEqual(self.path.read_bytes(), shared)

    def test_local_forward_and_three_reverse_switches_preserve_recipe_and_media(self):
        self.cycle()

    def test_real_git_public_reverse_cli_completes_three_round_trip_switches(self):
        self.git('init', '-q')
        (self.root/'.gitignore').write_text('/creative.config.local.json\n/host work/\n')
        self.cycle(cli=True)
        self.assertEqual(self.git('ls-files','creative.config.local.json').stdout, '')
