"""Inconsistent relocation evidence fails validation without leaking StopIteration."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
import staging_inventory


class StagingLayoutValidationTests(unittest.TestCase):
    def test_file_without_owned_group_has_explicit_validation_error(self):
        groups = {'workspace': Path('/verified')}
        staging = {'workspace': '/stage'}
        core = SimpleNamespace(config_path=Path('/project/config.json'),
                               _relocation_layout=lambda plan: ({'workspace': Path('/outside')}, groups, staging))
        intent = {'groups': {'workspace': '/verified'}, 'staging': staging}
        plan = {'id': 'move', 'config_path': str(core.config_path),
                'files': [{'root': 'workspace', 'path': 'record.json'}]}
        with patch.object(staging_inventory, '_record', side_effect=lambda core, identity, suffix:
                          intent if suffix == 'prepare-intent' else None), \
             patch('relocation_inventory._manifest'):
            with self.assertRaisesRegex(ValueError, 'group'):
                staging_inventory.inspect(core, plan)

    def test_retained_copy_without_verified_root_is_rejected(self):
        import tempfile
        from datetime import datetime, timezone
        import relocation_retention
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            core = SimpleNamespace(paths=SimpleNamespace(workspace=root),
                                   _live_configuration=lambda: {},
                                   _read=lambda *args: {'id': 'move', 'operation': 'reverse-relocation-plan',
                                                       'to': {'objects': str(root/'objects')}})
            snapshot = {'copies': [{'status': 'VERIFIED', 'relocation_id': 'move',
                                    'path': str(root/'missing'), 'group': 'workspace'}]}
            with patch.object(relocation_retention, 'inventory', return_value=snapshot), \
                 patch.object(relocation_retention, '_verified_roots', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'verified root'):
                    relocation_retention._state(core, datetime.now(timezone.utc))

    def test_cancelled_missing_staging_is_omitted_but_partial_cancel_is_retained(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            groups = {'workspace': root/'destination'}
            staging = {'workspace': str(root/'missing-stage')}
            core = SimpleNamespace(config_path=root/'config.json',
                                   _relocation_layout=lambda plan: ({}, groups, staging))
            plan = {'id': 'move', 'config_path': str(core.config_path), 'files': []}
            for phase in ('CANCELLED', 'CANCELLED_PARTIAL'):
                def record(core, identity, suffix):
                    if suffix == 'prepare-intent':
                        return {'groups': {k: str(v) for k,v in groups.items()}, 'staging': staging}
                    if suffix == 'cancelled': return {'status': phase}
                    if suffix == 'staging-root-workspace':
                        return {'group': 'workspace', 'path': staging['workspace'], 'directory_identity': [0,0]}
                    return None
                with patch.object(staging_inventory, '_record', side_effect=record), \
                     patch('relocation_inventory._manifest', return_value={}), \
                     patch('relocation_inventory._inspect', return_value=({'status': 'MISSING'}, {})):
                    rows, _ = staging_inventory.inspect(core, plan)
                self.assertEqual(len(rows), 0 if phase == 'CANCELLED' else 1)
