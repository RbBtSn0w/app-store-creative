"""Delivery status revalidates sealed evidence without implying remote completion."""
import json
from pathlib import Path
import unittest
import test_delivery_lifecycle as fixtures


class DeliveryStatusTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def sealed(self):
        validation, approval = self.approved()
        return self.store.seal(self.candidate['id'], validation['id'], approval['id'])

    def test_status_rechecks_package_and_does_not_write_records(self):
        delivery = self.sealed()
        records = self.store.paths.workspace / 'records'
        before = {path.relative_to(records): path.read_bytes() for path in records.rglob('*.json')}
        result = self.store.delivery_status(delivery['id'])
        self.assertEqual(result['local_status'], 'PASS')
        self.assertTrue(result['provenance_verified'])
        self.assertEqual(result['remote_status'], 'UNKNOWN')
        self.assertFalse(result['remote_write'])
        self.assertEqual({path.relative_to(records): path.read_bytes() for path in records.rglob('*.json')}, before)
        media = next((Path(delivery['local_path']) / 'media').rglob('*.png'))
        media.write_bytes(b'corrupt')
        self.assertEqual(self.store.delivery_status(delivery['id'])['local_status'], 'FAIL')

    def test_delivery_record_must_match_archive_identity_and_approval(self):
        delivery = self.sealed(); path = self.store._path('deliveries', delivery['id'])
        for change in ({'approval_id': 'other'}, {'validation_id': 'other'}, {'target': {'platform': 'IOS', 'version': '2'}}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**delivery, **change}))
                result = self.store.delivery_status(delivery['id'])
                self.assertEqual(result['local_status'], 'FAIL')
                self.assertTrue(result['errors'])

    def test_delivery_pages_remain_stable_when_new_archives_are_sealed(self):
        deliveries = [self.sealed() for _ in range(4)]
        first = self.store.list_deliveries(limit=2)
        self.assertEqual([item['id'] for item in first['deliveries']], [item['id'] for item in reversed(deliveries[-2:])])
        self.sealed()
        second = self.store.list_deliveries(limit=2, cursor=first['next_cursor'])
        self.assertEqual([item['id'] for item in second['deliveries']], [item['id'] for item in reversed(deliveries[:2])])
        self.assertIsNone(second['next_cursor'])
        self.assertTrue(all('package_verified' not in item for item in first['deliveries']))
        for limit in (True, 0, 101, '2'):
            with self.assertRaises(ValueError):
                self.store.list_deliveries(limit=limit)
        with self.assertRaises(ValueError):
            self.store.list_deliveries(cursor='missing')
