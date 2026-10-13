"""Design approval fixes the release target through seal and portable verification."""
import json
import unittest
from pathlib import Path
import test_delivery_lifecycle as fixtures
from delivery_lifecycle import verify_archive


class DesignTargetBindingTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_changed_run_target_cannot_reuse_design_approval(self):
        validation, approval = self.approved()
        path = self.store._path('runs', self.run['id'])
        run = json.loads(path.read_bytes()); run['target']['version'] = '2.0'
        path.write_text(json.dumps(run))
        changed_bytes = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Run commit event binding'):
            self.store.status(self.run['id'])
        with self.assertRaisesRegex(ValueError, 'Run commit event binding'):
            self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.assertEqual(path.read_bytes(), changed_bytes)
        self.assertEqual(list((self.store.paths.workspace / 'records/deliveries').glob('*.json')), [])

    def test_portable_archive_target_must_match_approved_target(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        package = Path(delivery['local_path'])
        manifest = json.loads((package / 'manifest.json').read_bytes())
        manifest['target']['version'] = '2.0'
        (package / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'approval|target'):
            verify_archive(package)
