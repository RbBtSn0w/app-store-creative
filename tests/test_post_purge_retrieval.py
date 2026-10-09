"""Redundant copy deletion preserves independently restorable sealed media."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_publication_lifecycle as fixtures
from artifact_lifecycle import Lifecycle
from delivery_lifecycle import verify_archive


class PostPurgeRetrievalTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp

    def test_public_restore_after_relocation_and_purge_preserves_existing_destination(self):
        self.store.config_path.write_text(json.dumps(self.config))
        storage = {'workspaceRoot': 'moved-work', 'objectRoot': 'moved-objects',
                   'releaseRoot': 'moved-releases', 'publicationRoot': 'moved-publications'}
        move = self.store.plan_relocation(storage)
        self.store.prepare_relocation(move['id'], 'fixture-owner', 'Disposable lifecycle drill')
        self.store.switch_relocation(move['id'], 'fixture-owner', 'Disposable lifecycle drill')
        active = Lifecycle.from_configuration(self.root, self.store.config_path)
        retention = active.plan_relocation_retention(retention_days=0)
        prepared = active.prepare_relocation_quarantine(retention['id'], 'fixture-owner', 'Disposable lifecycle drill')
        active.commit_relocation_quarantine(prepared['id'], 'fixture-owner', 'Disposable lifecycle drill')
        purge = active.plan_relocation_purge(prepared['id'], quarantine_days=0)
        active.purge_relocation(purge['id'], 'fixture-owner', 'Disposable lifecycle drill')
        self.assertTrue(purge['files'])
        self.assertTrue(all(not Path(item['path']).exists() for item in purge['files']))
        active.verify_artifact(self.output['id'])
        package = active.delivery_path(self.delivery)
        destination = self.root / 'independently-restored'
        script = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = [sys.executable, str(script), 'archive', 'restore', '--path', str(package),
                   '--destination', str(destination), '--expected-sha256', self.delivery['manifest_sha256']]
        restored = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        verify_archive(destination, self.delivery['manifest_sha256'])
        media = destination / 'media/en-US/mac_16_10/hero.png'
        self.assertEqual(media.read_bytes(), active.object_path(self.output['sha256']).read_bytes())
        note = destination / 'owner-note'; note.write_text('Preserve independent destination')
        refused = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(note.read_text(), 'Preserve independent destination')
        active.verify_artifact(self.output['id'])
