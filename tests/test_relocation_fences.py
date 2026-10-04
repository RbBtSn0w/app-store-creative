"""Old clients cannot mutate storage after a relocation write fence."""
import hashlib
from pathlib import Path
import unittest
import test_relocation_lifecycle as fixtures
from artifact_lifecycle import Lifecycle, canonical


class RelocationFenceTests(unittest.TestCase):
    setUp = fixtures.RelocationTests.setUp
    source = fixtures.RelocationTests.source
    targets = fixtures.RelocationTests.targets

    def fence(self):
        self.source(); plan = self.store.plan_relocation(self.targets())
        self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        with self.store.transaction():
            return self.store._fence_relocation_locked(plan['id'])

    def test_existing_client_cannot_start_run_after_fence(self):
        fence = self.fence()
        before = sorted((self.store.paths.workspace / 'records/runs').glob('*.json'))
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.start_run({})
        self.assertEqual(sorted((self.store.paths.workspace / 'records/runs').glob('*.json')), before)
        self.assertEqual(fence['from'], self.store.paths.binding())

    def test_fresh_client_cannot_plan_cleanup_after_fence(self):
        self.fence()
        fresh = Lifecycle(self.root, self.cfg)
        with self.assertRaisesRegex(ValueError, 'fenced'):
            fresh.plan_cleanup()

    def test_preparation_retry_is_fenced(self):
        fence = self.fence()
        with self.assertRaisesRegex(ValueError, 'fenced'):
            self.store.prepare_relocation(fence['relocation_id'], 'owner', 'Repeat')

    def test_unprepared_move_cannot_install_fence(self):
        self.source(); plan = self.store.plan_relocation(self.targets())
        with self.store.transaction():
            with self.assertRaisesRegex(ValueError, 'prepared'):
                self.store._fence_relocation_locked(plan['id'])
        self.store.start_run({})

    def test_stale_plan_cannot_install_fence(self):
        artifact = self.source(); plan = self.store.plan_relocation(self.targets())
        self.store.prepare_relocation(plan['id'], 'owner', 'Move')
        (self.store.paths.workspace / artifact['workspace_path']).write_bytes(b'changed')
        with self.store.transaction():
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.store._fence_relocation_locked(plan['id'])
        self.store.start_run({})

    def test_separate_cli_process_cannot_write_fenced_storage(self):
        import json
        import subprocess
        import sys
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        (self.root / 'target.json').write_text('{}')
        self.fence()
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'run', 'start', '--repo', str(self.root),
                                 '--target', 'target.json'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fenced', result.stderr)
