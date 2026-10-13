"""Configuration relocation requires explicit, byte-bound local authority."""
import json
import unittest
from pathlib import Path
import test_configuration_layers as fixtures
from artifact_lifecycle import Lifecycle

class ConfigurationLocationMigrationTests(unittest.TestCase):
    setUp = fixtures.ConfigurationLayersTests.setUp
    def prepared(self):
        from configuration_location import relocate_configuration
        core = Lifecycle.from_configuration(self.root)
        run = core.start_run({})
        attempt = core.start_attempt(run['id'], 'render', 'fixture')
        source = core.work_path(attempt['id']) / 'media'
        source.write_bytes(b'preserved')
        artifact = core.register(attempt['id'], source, 'source')
        core.finish_attempt(attempt['id'], 'succeeded')
        target = self.root / 'stable'
        storage = {k:str(target/v) for k,v in [('workspaceRoot','working'),('objectRoot','objects'),('releaseRoot','releases'),('publicationRoot','publications')]}
        plan = core.plan_relocation(storage)
        core.prepare_relocation(plan['id'], 'fixture', 'Stable storage')
        core.switch_relocation(plan['id'], 'fixture', 'Stable storage')
        return Lifecycle.from_configuration(self.root), target, artifact, relocate_configuration
    def test_explicit_migration_survives_original_configuration_removal(self):
        core,target,artifact,migrate=self.prepared()
        result=migrate(core,target,'fixture','Move configuration')
        self.assertEqual(result['status'],'ACTIVATED')
        self.path.unlink()
        moved=Lifecycle.from_configuration(target)
        moved.verify_artifact(artifact['id'])
        moved.start_run({})
        moved.start_attempt(artifact['run_id'], 'render', 'fixture')
        self.assertEqual(moved.verify_history()['status'],'PASS')
    def test_copy_without_authority_remains_refused(self):
        core,target,artifact,_=self.prepared()
        (target/'creative.config.json').write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(ValueError,'activation evidence'):
            Lifecycle.from_configuration(target).start_attempt(artifact['run_id'], 'render', 'fixture')
    def test_target_configuration_tampering_remains_refused(self):
        core,target,artifact,migrate=self.prepared()
        migrate(core,target,'fixture','Move configuration')
        p=target/'creative.config.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'configuration'):
            Lifecycle.from_configuration(target).start_attempt(artifact['run_id'], 'render', 'fixture')
    def test_repeated_execution_does_not_overwrite_changed_target(self):
        core,target,_,migrate=self.prepared()
        first=migrate(core,target,'fixture','Move configuration')
        self.assertEqual(migrate(core,target,'fixture','Move configuration'),first)
        p=target/'creative.config.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(ValueError):migrate(core,target,'fixture','Move configuration')

    def test_original_configuration_is_fenced_after_activation(self):
        core,target,_,migrate=self.prepared()
        migrate(core,target,'fixture','Move configuration')
        with self.assertRaisesRegex(ValueError,'authority relocated'):
            core.start_run({})
    def test_altered_authority_receipt_is_refused(self):
        from configuration_location import key
        core,target,artifact,migrate=self.prepared()
        migrate(core,target,'fixture','Move configuration')
        path=core._path('configuration-locations',key(core.config_path))
        data=json.loads(path.read_text());data['reason']='changed';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'commit event'):
            Lifecycle.from_configuration(target).start_attempt(artifact['run_id'], 'render', 'fixture')

    def test_changed_target_before_commit_preserves_source_authority(self):
        from unittest.mock import patch
        import configuration_location
        core,target,_,migrate=self.prepared()
        original=configuration_location.load
        def changed(root,path):
            if Path(path).parent == target:
                Path(path).write_bytes(Path(path).read_bytes()+b' ')
            return original(root,path)
        with patch.object(configuration_location,'load',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Configuration bytes'):
                migrate(core,target,'fixture','Move configuration')
        core.start_run({})

    def test_original_config_cannot_adopt_another_project_root(self):
        core,target,_,_=self.prepared()
        with self.assertRaisesRegex(ValueError,'owned by another project'):
            Lifecycle.from_configuration(self.root/'unapproved',self.path).start_run({})
    def test_public_cli_transfers_local_configuration_and_backend_access(self):
        import subprocess
        import sys
        fixtures.ConfigurationLayersTests.write_local(self, mediaBackends={
            'receipts':{'provider':'filesystem','root':str(self.root/'backend')}})
        self.local.chmod(0o600)
        core,target,artifact,_=self.prepared()
        script=Path(__file__).parents[1]/'plugins/app-store-creative/scripts/app_store_creative.py'
        result=subprocess.run([sys.executable,str(script),'storage','relocate-configuration',
            '--repo',str(self.root),'--destination',str(target),'--actor','fixture',
            '--reason','Move configuration','--confirm','RELOCATE'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'ACTIVATED')
        self.assertEqual((target/'creative.config.local.json').stat().st_mode & 0o777,0o600)
        self.assertEqual(Lifecycle.from_configuration(target)._configuration_layers.local_config['mediaBackends'],core._configuration_layers.local_config['mediaBackends'])
        self.path.unlink();self.local.unlink()
        Lifecycle.from_configuration(target).start_attempt(artifact['run_id'],'render','fixture')
    def test_second_destination_is_refused_without_writes(self):
        core,target,_,migrate=self.prepared()
        migrate(core,target,'fixture','Move configuration')
        other=self.root/'other'
        with self.assertRaisesRegex(ValueError,'elsewhere'):
            migrate(core,other,'fixture','Move elsewhere')
        self.assertFalse(other.exists())

    def test_relative_storage_roots_cannot_transfer_authority(self):
        from configuration_location import relocate_configuration
        core = Lifecycle.from_configuration(self.root)
        core.start_run({})
        with self.assertRaisesRegex(ValueError, 'storage roots'):
            relocate_configuration(core, self.root / 'other', 'fixture', 'Move configuration')
        core.start_run({})

    def test_preexisting_private_configuration_with_open_permissions_is_refused(self):
        fixtures.ConfigurationLayersTests.write_local(self, mediaBackends={
            'receipts': {'provider': 'filesystem', 'root': str(self.root / 'backend')}})
        self.local.chmod(0o600)
        core, target, _, migrate = self.prepared()
        target.mkdir(parents=True, exist_ok=True)
        (target / 'creative.config.json').write_bytes(self.path.read_bytes())
        private = target / 'creative.config.local.json'
        private.write_bytes(self.local.read_bytes())
        private.chmod(0o644)
        with self.assertRaises(ValueError):
            migrate(core, target, 'fixture', 'Move configuration')
        self.assertEqual(private.stat().st_mode & 0o777, 0o644)
        core.start_run({})

    def test_storage_relocation_after_configuration_transfer_keeps_authority(self):
        core, target, artifact, migrate = self.prepared()
        migrate(core, target, 'fixture', 'Move configuration')
        moved = Lifecycle.from_configuration(target)
        next_root = self.root / 'next-storage'
        roots = {k: str(next_root / v) for k, v in [
            ('workspaceRoot', 'working'), ('objectRoot', 'objects'),
            ('releaseRoot', 'releases'), ('publicationRoot', 'publications')]}
        plan = moved.plan_relocation(roots)
        moved.prepare_relocation(plan['id'], 'fixture', 'Move storage again')
        moved.switch_relocation(plan['id'], 'fixture', 'Move storage again')
        active = Lifecycle.from_configuration(target)
        active.start_run({})
        active.verify_artifact(artifact['id'])

    def test_storage_round_trip_after_configuration_transfer_keeps_authority(self):
        core, target, artifact, migrate = self.prepared()
        migrate(core, target, 'fixture', 'Move configuration')
        moved = Lifecycle.from_configuration(target)
        next_root = self.root / 'next-storage'
        roots = {k: str(next_root / v) for k, v in [
            ('workspaceRoot', 'working'), ('objectRoot', 'objects'),
            ('releaseRoot', 'releases'), ('publicationRoot', 'publications')]}
        plan = moved.plan_relocation(roots)
        moved.prepare_relocation(plan['id'], 'fixture', 'Move storage again')
        moved.switch_relocation(plan['id'], 'fixture', 'Move storage again')
        active = Lifecycle.from_configuration(target)
        reverse = active.plan_reverse_relocation(plan['id'])
        active.prepare_reverse_relocation(reverse['id'], 'fixture', 'Return storage')
        active.switch_reverse_relocation(reverse['id'], 'fixture', 'Return storage')
        returned = Lifecycle.from_configuration(target)
        returned.start_run({})
        returned.verify_artifact(artifact['id'])
