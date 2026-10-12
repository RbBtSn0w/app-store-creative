"""Opt-in real-volume reuse of the public relocation crash recovery matrix."""
import os
from pathlib import Path
import tempfile
import unittest
import test_relocation_process_crash as fixtures


class CrossFilesystemProcessCrashTests(fixtures.RelocationProcessCrashTests):
    def setUp(self):
        value = os.environ.get('CREATIVE_TEST_CROSSFS_ROOT')
        if not value:
            self.skipTest('Explicit independently mounted test volume required')
        volume = Path(value).resolve(strict=True)
        super().setUp()
        if volume.stat().st_dev == self.root.stat().st_dev:
            self.skipTest('Requested test volume shares the source filesystem')
        self.volume_workspace = tempfile.TemporaryDirectory(prefix='creative-owned-', dir=volume)
        self.addCleanup(self.volume_workspace.cleanup)
        self.volume_root = Path(self.volume_workspace.name)
        self.assertNotEqual(self.root.stat().st_dev, self.volume_root.stat().st_dev)

    def targets(self):
        return {key: str(self.volume_root / name) for key, name in
                [('workspaceRoot', 'work'), ('objectRoot', 'media'),
                 ('releaseRoot', 'releases'), ('publicationRoot', 'publications')]}
