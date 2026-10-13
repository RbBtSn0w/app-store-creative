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
