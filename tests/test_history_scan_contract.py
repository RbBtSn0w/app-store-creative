"""Strict history scans reject unsupported entries instead of skipping evidence."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
from inventory_lifecycle import files_without_links


class HistoryScanContractTests(unittest.TestCase):
    def test_strict_scan_returns_regular_records_and_reports_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            record = root / 'record.json'; record.write_text('{}')
            link = root / 'alias'; link.symlink_to(record)
            files, links = files_without_links(root, strict=True)
            self.assertEqual(files, [record])
            self.assertEqual(links, [link])

    def test_strict_scan_rejects_fifo_and_non_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fifo = root / 'fifo'; os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                files_without_links(root, strict=True)
            with self.assertRaises(NotADirectoryError):
                files_without_links(fifo, strict=True)

    def test_abandonment_without_commit_evidence_fails_validation(self):
        from types import SimpleNamespace
        from operation_history import verify
        import json
        from unittest.mock import patch
        reader = SimpleNamespace(_read_regular=lambda path: path.read_bytes(),
                                 _document=json.loads)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            records = root / 'records' / 'commit-abandonments'; records.mkdir(parents=True)
            (records / 'decision.json').write_text('{}')
            core = SimpleNamespace(paths=SimpleNamespace(workspace=root),
                                   _assert_paths=lambda: None,
                                   _live_configuration=lambda: None,
                                   _read=lambda *args: {})
            with self.assertRaisesRegex(ValueError, 'commit evidence'):
                with patch.dict(sys.modules, {'configuration_layers': reader}):
                    verify(core, locked=True)
