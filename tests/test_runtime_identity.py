"""Producer payload fingerprints survive archive export without machine paths."""
import json
from pathlib import Path
import tempfile
import unittest
import test_delivery_lifecycle as fixtures
from runtime_identity import snapshot, validate


class RuntimeIdentityTests(unittest.TestCase):
    def test_fingerprint_is_location_independent_and_changes_with_source(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory).resolve() / 'first'; first.mkdir()
            second = Path(directory).resolve() / 'second'; second.mkdir()
            for root in (first, second):
                (root / 'producer.py').write_text('implementation = 1\n')
            self.assertEqual(snapshot(first), snapshot(second))
            (second / 'producer.py').write_text('implementation = 2\n')
            self.assertNotEqual(snapshot(first), snapshot(second))
            self.assertNotIn(directory, json.dumps(snapshot(first)))

    def test_invalid_or_aliased_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            validate({'scheme': 'source-payload-sha256-v1', 'sha256': '0' * 64, 'file_count': True})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'source'; source.write_text('implementation')
            (root / 'producer.py').symlink_to(source)
            with self.assertRaisesRegex(ValueError, 'regular'):
                snapshot(root)

    def test_sealed_provenance_binds_each_producing_attempt_implementation(self):
        fixture = fixtures.DeliveryLifecycleTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        validation, approval = fixture.approved()
        delivery = fixture.store.seal(fixture.candidate['id'], validation['id'], approval['id'])
        provenance = json.loads((Path(delivery['local_path']) / 'evidence/provenance.json').read_text())
        for node in provenance['nodes']:
            attempt = fixture.store._read('attempts', node['attempt_id'], 'started')
            self.assertEqual(node['implementation'], attempt['implementation'])
            validate(node['implementation'])
        self.assertNotIn(str(fixture.root), json.dumps(provenance))
