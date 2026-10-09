"""Local approvals require the same policy and run binding as portable archives."""
import json
import unittest
import test_delivery_lifecycle as fixtures


class ValidationPolicyBindingTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp

    def test_invalid_validation_cannot_create_approval(self):
        validation = self.store.validate_candidate(self.candidate['id'])
        path = self.store._path('validations', validation['id'])
        directory = self.store.paths.workspace / 'records/approvals'
        for change in ({'policy_version': 'future'}, {'run_id': 'other'}, {'errors': ['Failure']}, {'errors': None}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**validation, **change}))
                with self.assertRaisesRegex(ValueError, 'validation'):
                    self.store.approve_design(self.candidate['id'], validation['id'], 'owner', 'human:approval')
                self.assertEqual(list(directory.glob('*.json')), [])
