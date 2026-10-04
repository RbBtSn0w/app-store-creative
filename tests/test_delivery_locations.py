"""Archived package lookup follows verified placement without rewriting delivery."""
import copy
import hashlib
from pathlib import Path
import unittest
import test_delivery_lifecycle as fixtures
from artifact_lifecycle import canonical


class DeliveryLocationTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def sealed(self):
        validation, approval = self.approved()
        return self.store.seal(self.candidate['id'], validation['id'], approval['id'])

    def historical(self, delivery):
        current = self.store.paths.binding(); old = {**current, 'releases': str(self.root / 'old archives')}
        switched = self.store._record('relocations', {'id': 'move', 'status': 'SWITCHED',
            'from': old, 'to': current, 'config_path': str(self.store.config_path),
            'project_id': self.config['project']['id']}, 'switched')
        self.store._record('storage-bindings', {'id': hashlib.sha256(canonical(old)).hexdigest(),
            'from': old, 'to': current, 'relocation_id': 'move',
            'switch_sha256': hashlib.sha256(canonical(switched)).hexdigest()})
        record = copy.deepcopy(delivery); record['storage'] = old
        relative = Path(delivery['local_path']).relative_to(current['releases'])
        record['local_path'] = str(Path(old['releases']) / relative)
        return record

    def test_seal_records_original_binding_and_relative_archive_location(self):
        delivery = self.sealed()
        self.assertEqual(delivery['storage'], self.store.paths.binding())
        self.assertEqual(self.store.delivery_path(delivery), Path(delivery['local_path']))

    def test_historical_archive_resolves_to_verified_current_package(self):
        delivery = self.sealed(); historical = self.historical(delivery); before = canonical(historical)
        self.assertEqual(self.store.delivery_path(historical), Path(delivery['local_path']))
        self.assertEqual(canonical(historical), before)

    def test_location_outside_original_archive_root_is_rejected(self):
        record = self.historical(self.sealed()); record['local_path'] = str(self.root / 'private')
        with self.assertRaisesRegex(ValueError, 'archive root'):
            self.store.delivery_path(record)

    def test_package_corruption_after_move_is_rejected(self):
        delivery = self.sealed(); record = self.historical(delivery)
        (Path(delivery['local_path']) / 'manifest.json').write_bytes(b'broken')
        with self.assertRaises(ValueError):
            self.store.delivery_path(record)
