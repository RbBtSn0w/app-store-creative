"""Archive declarations fail consistently before reading invalid containers."""
import unittest
from archive_policy import resolve


class ArchivePolicyValidationTests(unittest.TestCase):
    def test_non_object_configuration_is_rejected(self):
        for value in (None, [], 'archivePolicy', 1, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'configuration'):
                    resolve(value)
