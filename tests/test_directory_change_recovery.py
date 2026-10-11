"""Root recovery recognizes completed swaps rather than reversing them."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import delivery_lifecycle as directories


class DirectoryChangeRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='creative-root-recovery-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.staging = self.root / 'staging'; self.staging.mkdir()
        (self.staging / 'new.txt').write_text('New data')
        self.destination = self.root / 'original'; self.destination.mkdir()
        (self.destination / 'old.txt').write_text('Preserved old data')

    def change(self, operation='EXCHANGE'):
        source = self.staging.stat()
        target = self.destination.stat() if self.destination.exists() else None
        return {'operation': operation, 'staging': str(self.staging),
                'destination': str(self.destination),
                'staging_identity': [source.st_dev, source.st_ino],
                'destination_identity': [target.st_dev, target.st_ino] if target else None}

    def test_completed_exchange_retry_does_not_swap_back(self):
        change = self.change()
        result = directories.apply_directory_change(change)
        self.assertEqual(result['status'], 'APPLIED')
        result = directories.apply_directory_change(change)
        self.assertEqual(result['status'], 'ALREADY_APPLIED')
        self.assertEqual((self.destination / 'new.txt').read_text(), 'New data')
        self.assertEqual((self.staging / 'old.txt').read_text(), 'Preserved old data')

    def test_retry_after_sync_failure_preserves_exchange_direction(self):
        change = self.change()
        with patch('delivery_lifecycle.os.fsync', side_effect=OSError('Sync failed')):
            for retry in range(2):
                with self.assertRaisesRegex(OSError, 'Sync failed'):
                    directories.apply_directory_change(change)
        self.assertEqual(directories.apply_directory_change(change)['status'], 'ALREADY_APPLIED')
        self.assertTrue((self.destination / 'new.txt').is_file())
        self.assertTrue((self.staging / 'old.txt').is_file())

    def test_replaced_destination_refused_without_mutation(self):
        change = self.change()
        backup = self.root / 'backup'; self.destination.rename(backup)
        self.destination.mkdir(); (self.destination / 'old.txt').write_text('Preserved old data')
        with self.assertRaisesRegex(ValueError, 'identity'):
            directories.apply_directory_change(change)
        self.assertTrue((self.staging / 'new.txt').is_file())
        self.assertTrue((backup / 'old.txt').is_file())

    def test_absent_root_publication_is_retryable(self):
        import shutil
        shutil.rmtree(self.destination)
        change = self.change('PUBLISH')
        self.assertEqual(directories.apply_directory_change(change)['status'], 'APPLIED')
        self.assertEqual(directories.apply_directory_change(change)['status'], 'ALREADY_APPLIED')
        self.assertFalse(self.staging.exists())
        self.assertTrue((self.destination / 'new.txt').is_file())

    def test_revert_exchange_and_retry_preserve_original_direction(self):
        change = self.change()
        directories.apply_directory_change(change)
        self.assertEqual(directories.revert_directory_change(change)['status'], 'REVERTED')
        self.assertEqual(directories.revert_directory_change(change)['status'], 'ALREADY_REVERTED')
        self.assertEqual((self.destination / 'old.txt').read_text(), 'Preserved old data')
        self.assertEqual((self.staging / 'new.txt').read_text(), 'New data')

    def test_revert_sync_failure_retry_does_not_apply_again(self):
        change = self.change()
        directories.apply_directory_change(change)
        with patch('delivery_lifecycle.os.fsync', side_effect=OSError('Revert sync failed')):
            for retry in range(2):
                with self.assertRaisesRegex(OSError, 'Revert sync failed'):
                    directories.revert_directory_change(change)
        self.assertEqual(directories.revert_directory_change(change)['status'], 'ALREADY_REVERTED')
        self.assertTrue((self.destination / 'old.txt').is_file())
        self.assertTrue((self.staging / 'new.txt').is_file())

    def test_revert_publication_returns_data_to_staging(self):
        import shutil
        shutil.rmtree(self.destination)
        change = self.change('PUBLISH')
        directories.apply_directory_change(change)
        self.assertEqual(directories.revert_directory_change(change)['status'], 'REVERTED')
        self.assertFalse(self.destination.exists())
        self.assertTrue((self.staging / 'new.txt').is_file())
        self.assertEqual(directories.revert_directory_change(change)['status'], 'ALREADY_REVERTED')

    def test_revert_refuses_replaced_backup(self):
        change = self.change()
        directories.apply_directory_change(change)
        displaced = self.root / 'original-backup'
        self.staging.rename(displaced); self.staging.mkdir()
        (self.staging / 'old.txt').write_text('Preserved old data')
        with self.assertRaisesRegex(ValueError, 'identity'):
            directories.revert_directory_change(change)
        self.assertTrue((self.destination / 'new.txt').is_file())
        self.assertTrue((displaced / 'old.txt').is_file())
