"""The common record reader refuses byte changes against the original commit."""
import json
import unittest
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import identifier
from operation_history import CATEGORIES


class RecordCommitConsumptionTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_common_commit_boundary_for_all_business_record_categories(self):
        for category in sorted(CATEGORIES):
            with self.subTest(category=category):
                if category == 'runs':
                    record = self.store.start_run({})
                else:
                    data = {'id': identifier()}
                    if category == 'remote-observations':
                        data['evidence_sha256'] = '0' * 64
                    record = self.store._record(category, data)
                path = self.store._path(category, record['id'])
                original = path.read_bytes()
                data = json.loads(original)
                data['contract_probe'] = 'changed after original commit'
                changed = json.dumps(data).encode()
                path.write_bytes(changed)
                try:
                    with self.assertRaisesRegex(ValueError, 'commit event'):
                        if category == 'runs':
                            self.store._run(record['id'])
                        else:
                            self.store._read(category, record['id'])
                    self.assertEqual(path.read_bytes(), changed)
                finally:
                    path.write_bytes(original)
