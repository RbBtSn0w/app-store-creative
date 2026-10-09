"""Local owning-layer forward migration includes interrupted recovery."""
import unittest
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle
from relocation_lifecycle import recovery_source


class LocalForwardExecutionTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    write_local = fixtures.ConfigurationLayersTests.write_local
    git = fixtures.ConfigurationLayersTests.git

    def prepared(self):
        self.write_local(); self.local.chmod(0o600)
        core = Lifecycle.from_configuration(self.root, self.path)
        run = core.start_run({}); attempt = core.start_attempt(run['id'], 'render', 'fixture')
        source = core.work_path(attempt['id'])/'media'; source.write_bytes(b'preserved media')
        artifact = core.register(attempt['id'], source, 'source'); core.finish_attempt(attempt['id'], 'succeeded')
        plan = core.plan_relocation({'workspaceRoot':'next host'})
        if (self.root/'.git').exists():
            policy = core.relocation_git_policy(plan['id'])
            rules = self.root/'.gitignore'
            rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
        core.prepare_relocation(plan['id'], 'fixture', 'Prepare local migration')
        return core, plan, artifact

    def test_forward_switch_preserves_shared_document_and_media(self):
        shared = self.path.read_bytes(); core, plan, artifact = self.prepared()
        core.switch_relocation(plan['id'], 'fixture', 'Switch local migration')
        moved = Lifecycle.from_configuration(self.root, self.path)
        self.assertEqual(moved.paths.workspace, self.root/'next host')
        moved.verify_artifact(artifact['id']); moved.start_run({})
        self.assertEqual(self.path.read_bytes(), shared)
        self.assertEqual(self.local.stat().st_mode & 0o777, 0o600)

    def test_post_install_interruption_can_resume_from_recorded_source(self):
        shared = self.path.read_bytes(); core, plan, artifact = self.prepared()
        with patch.object(core, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError): core.switch_relocation(plan['id'], 'fixture', 'Switch')
        recovered = recovery_source(self.root, self.path, core.paths.workspace, plan['id'])
        recovered.resume_relocation(plan['id'], 'fixture', 'Resume')
        Lifecycle.from_configuration(self.root, self.path).verify_artifact(artifact['id'])
        self.assertEqual(self.path.read_bytes(), shared)

    def test_post_install_interruption_can_restore_original_local_bytes(self):
        core, plan, artifact = self.prepared(); local = self.local.read_bytes(); shared = self.path.read_bytes()
        with patch.object(core, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError): core.switch_relocation(plan['id'], 'fixture', 'Switch')
        recovered = recovery_source(self.root, self.path, core.paths.workspace, plan['id'])
        recovered.rollback_relocation(plan['id'], 'fixture', 'Rollback')
        self.assertEqual(self.local.read_bytes(), local); self.assertEqual(self.path.read_bytes(), shared)
        Lifecycle.from_configuration(self.root, self.path).verify_artifact(artifact['id'])

    def test_shared_recipe_change_after_local_installation_refuses_recovery(self):
        core, plan, _ = self.prepared()
        with patch.object(core, '_sync_configuration_directory', side_effect=OSError('Sync interrupted')):
            with self.assertRaises(OSError): core.switch_relocation(plan['id'], 'fixture', 'Switch')
        recovered = recovery_source(self.root, self.path, core.paths.workspace, plan['id'])
        self.path.write_bytes(self.path.read_bytes() + b' ')
        local = self.local.read_bytes()
        with self.assertRaisesRegex(ValueError, 'project.*changed|shared.*changed'):
            recovered.resume_relocation(plan['id'], 'fixture', 'Resume')
        self.assertEqual(self.local.read_bytes(), local)

    def test_public_cli_switch_in_real_git_workspace_uses_local_layer(self):
        self.git('init', '-q')
        (self.root/'.gitignore').write_text('/creative.config.local.json\n/host work/\n')
        core, plan, artifact = self.prepared(); shared = self.path.read_bytes()
        script = Path(__file__).parents[1]/'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(script), 'storage', 'switch-relocate',
            '--id', plan['id'], '--actor', 'fixture', '--reason', 'Verified local CLI migration',
            '--confirm', 'SWITCH', '--repo', str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'SWITCHED')
        moved = Lifecycle.from_configuration(self.root, self.path)
        moved.verify_artifact(artifact['id']); moved.start_run({})
        self.assertEqual(moved.paths.workspace, self.root/'next host')
        self.assertEqual(self.path.read_bytes(), shared)
        self.assertEqual(self.git('ls-files','creative.config.local.json').stdout, '')
