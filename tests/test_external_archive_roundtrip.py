"""Metadata-only copies restore complete approved archives from stable objects."""
import shutil
import unittest
import test_delivery_lifecycle as fixtures
from delivery_lifecycle import verify_archive
from external_delivery_archive import externalize, restore_external


class ExternalDeliveryArchiveTests(unittest.TestCase):
    archive_policy = {'schema_version': 1, 'mediaMode': 'external', 'backend': 'team'}
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved=fixtures.DeliveryLifecycleTests.approved

    def bundle(self):
        validation,approval=self.approved()
        delivery=self.store.seal(self.candidate['id'],validation['id'],approval['id'])
        result=externalize(delivery['local_path'],self.root/'metadata','team',self.root/'backend',delivery['manifest_sha256'])
        return delivery,result

    def test_metadata_only_copy_restores_without_original_archive_or_workspace(self):
        delivery,result=self.bundle()
        clone=self.root/'clean-copy';shutil.copytree(self.root/'metadata',clone)
        shutil.rmtree(delivery['local_path']);shutil.rmtree(self.store.paths.workspace)
        restored=restore_external(clone,self.root/'restored','team',self.root/'backend',result['descriptor_sha256'])
        self.assertTrue(restored['package_verified'])
        self.assertEqual(restored['provenance_verified'],
                         verify_archive(self.root/'restored').get('provenance_verified', False))
        self.assertEqual(verify_archive(self.root/'restored')['manifest_sha256'],delivery['manifest_sha256'])
        self.assertFalse((clone/'archive/media').exists())
        self.assertNotIn(str(self.root),(clone/'external.json').read_text())

    def test_wrong_descriptor_hash_is_rejected_before_restore(self):
        _,result=self.bundle()
        with self.assertRaisesRegex(ValueError,'descriptor'):
            restore_external(self.root/'metadata',self.root/'restored','team',self.root/'backend','0'*64)
        self.assertFalse((self.root/'restored').exists())

    def test_missing_external_object_does_not_publish_partial_archive(self):
        _,result=self.bundle()
        from external_media_store import FileSystemMediaStore
        import json
        descriptor=json.loads((self.root/'metadata/external.json').read_text())
        reference=descriptor['objects'][0]['reference']
        FileSystemMediaStore('team',self.root/'backend').object_path(reference).unlink()
        with self.assertRaisesRegex(ValueError,'missing'):
            restore_external(self.root/'metadata',self.root/'restored','team',self.root/'backend',result['descriptor_sha256'])
        self.assertFalse((self.root/'restored').exists())

