"""Atomic root exchange preserves both directory copies for recovery."""
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import delivery_lifecycle as directories


class DirectoryExchangeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='creative-exchange-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.original = self.root / 'original'
        self.staging = self.root / 'staging'
        self.original.mkdir(); self.staging.mkdir()
        (self.original / 'old.txt').write_text('Original preserved data')
        (self.staging / 'new.txt').write_text('Prepared current data')

    def test_exchange_preserves_both_directory_identities_and_bytes(self):
        original_inode = self.original.stat().st_ino
        staging_inode = self.staging.stat().st_ino
        result = directories.exchange_directories(self.staging, self.original)
        self.assertEqual(self.original.stat().st_ino, staging_inode)
        self.assertEqual(self.staging.stat().st_ino, original_inode)
        self.assertEqual((self.original / 'new.txt').read_text(), 'Prepared current data')
        self.assertEqual((self.staging / 'old.txt').read_text(), 'Original preserved data')
        self.assertTrue(result['parent_directories_synced'])

    def test_symlink_or_non_directory_refused_before_mutation(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.original, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'regular directory'):
            directories.exchange_directories(self.staging, alias)
        with self.assertRaisesRegex(ValueError, 'regular directory'):
            directories.exchange_directories(self.staging, self.original / 'old.txt')
        self.assertTrue((self.original / 'old.txt').is_file())
        self.assertTrue((self.staging / 'new.txt').is_file())

    def test_identical_or_nested_roots_refused(self):
        with self.assertRaisesRegex(ValueError, 'distinct|overlap'):
            directories.exchange_directories(self.original, self.original)
        nested = self.original / 'nested'; nested.mkdir()
        with self.assertRaisesRegex(ValueError, 'overlap'):
            directories.exchange_directories(nested, self.original)

    def test_sync_failure_keeps_exchanged_copies_for_recovery(self):
        with patch('delivery_lifecycle.os.fsync', side_effect=OSError('Parent sync failed')):
            with self.assertRaisesRegex(OSError, 'Parent sync failed'):
                directories.exchange_directories(self.staging, self.original)
        self.assertTrue((self.original / 'new.txt').is_file())
        self.assertTrue((self.staging / 'old.txt').is_file())

    def test_unsupported_platform_refused_without_changes(self):
        with patch('delivery_lifecycle.sys.platform', 'unsupported'):
            with self.assertRaisesRegex(ValueError, 'Atomic directory exchange is unavailable'):
                directories.exchange_directories(self.staging, self.original)
        self.assertTrue((self.original / 'old.txt').is_file())
        self.assertTrue((self.staging / 'new.txt').is_file())

    def test_native_rejection_preserves_original_locations(self):
        import ctypes
        from types import SimpleNamespace
        from unittest.mock import Mock
        def denied(*args):
            ctypes.set_errno(errno.EACCES)
            return -1
        call = Mock(side_effect=denied)
        library = SimpleNamespace(renameatx_np=call, renameat2=call)
        with patch('delivery_lifecycle.ctypes.CDLL', return_value=library):
            with self.assertRaises(OSError) as caught:
                directories.exchange_directories(self.staging, self.original)
        self.assertEqual(caught.exception.errno, errno.EACCES)
        self.assertTrue((self.original / 'old.txt').is_file())
        self.assertTrue((self.staging / 'new.txt').is_file())

    def test_changed_root_before_native_call_is_refused(self):
        import os
        original_open = os.open
        displaced = self.root / 'displaced-original'
        changed = []
        def race(path, flags, *args, **kwargs):
            if not changed:
                self.original.rename(displaced)
                self.original.mkdir()
                (self.original / 'owner-note').write_text('Concurrent replacement')
                changed.append(True)
            return original_open(path, flags, *args, **kwargs)
        with patch('delivery_lifecycle.os.open', side_effect=race):
            with self.assertRaisesRegex(ValueError, 'roots changed'):
                directories.exchange_directories(self.staging, self.original)
        self.assertTrue((displaced / 'old.txt').is_file())
        self.assertTrue((self.original / 'owner-note').is_file())
        self.assertTrue((self.staging / 'new.txt').is_file())
