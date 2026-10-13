"""Resolved root labels do not depend on default dictionary insertion order."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
import storage_configuration


class StoragePreviewMappingTests(unittest.TestCase):
    def test_reordered_defaults_preserve_root_labels(self):
        paths = SimpleNamespace(workspace=Path('/work'), objects=Path('/objects'),
                                releases=Path('/releases'), publications=Path('/publications'),
                                binding=lambda: {})
        defaults = dict(reversed(list(storage_configuration.STORAGE_DEFAULTS.items())))
        with patch.object(storage_configuration, 'check_config'), \
             patch.object(storage_configuration.StoragePaths, 'resolve', return_value=paths), \
             patch.dict(storage_configuration.STORAGE_DEFAULTS, defaults, clear=True):
            report = storage_configuration.preview(Path('/project'), {})
        self.assertEqual(report['roots']['workspaceRoot']['resolved'], '/work')
        self.assertEqual(report['roots']['objectRoot']['resolved'], '/objects')
        self.assertEqual(report['roots']['releaseRoot']['resolved'], '/releases')
        self.assertEqual(report['roots']['publicationRoot']['resolved'], '/publications')
