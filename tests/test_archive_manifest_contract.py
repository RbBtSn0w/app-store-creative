"""Portable archives require typed manifests and consistent media/source bindings."""
import copy
import json
from pathlib import Path
import unittest
import test_delivery_lifecycle as fixtures
from delivery_lifecycle import verify_archive


class ArchiveManifestContractTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_invalid_manifest_types_and_bindings_are_rejected(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        package = Path(delivery['local_path'])
        path = package / 'manifest.json'
        original = json.loads(path.read_text())
        mutations = []
        for version in (True, 1.0, 2):
            data = copy.deepcopy(original); data['schema_version'] = version; mutations.append(data)
        for field in ('files', 'assets', 'recipe_inputs'):
            data = copy.deepcopy(original); data[field] = {}; mutations.append(data)
        for field in ('assets', 'recipe_inputs'):
            data = copy.deepcopy(original); data[field][0]['sha256'] = '0' * 64; mutations.append(data)
        for index, data in enumerate(mutations + [[], None]):
            with self.subTest(case=index):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    verify_archive(package)

    def test_archive_rejects_namespace_role_identity_and_coverage_mismatches(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        package = Path(delivery['local_path']); path = package / 'manifest.json'
        original = json.loads(path.read_text()); mutations = []
        for field in ('assets', 'recipe_inputs'):
            data = copy.deepcopy(original)
            evidence = next(item for item in data['files'] if item['path'].startswith('evidence/'))
            data[field][0].update(path=evidence['path'], sha256=evidence['sha256']); mutations.append(data)
            data = copy.deepcopy(original); data[field].append(copy.deepcopy(data[field][0])); mutations.append(data)
            data = copy.deepcopy(original); data[field][0]['artifact_id'] = None; mutations.append(data)
        data = copy.deepcopy(original); data['assets'][0]['role'] = 'producer-evidence'; mutations.append(data)
        data = copy.deepcopy(original); data['recipe_inputs'] = []; mutations.append(data)
        for index, data in enumerate(mutations):
            with self.subTest(case=index):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    verify_archive(package)


class ImportedArchiveBindingTests(unittest.TestCase):
    def setUp(self):
        import test_input_lifecycle
        self.fixture = test_input_lifecycle.InputTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_alias_index_semantics_are_verified_even_with_matching_file_hash(self):
        from unittest.mock import patch
        import artifact_lifecycle as lifecycle
        import production_lifecycle
        from input_lifecycle import SNAPSHOT_INDEX
        fixture = self.fixture
        core = lifecycle.Lifecycle(fixture.root, fixture.config)
        imported = core.import_capture((fixture.root / 'capture.png').read_bytes(), 'capture.png', actor='owner')
        fixture.config['cards'][0]['screenshot'] = imported['path']
        fixture.cfg.write_text(json.dumps(fixture.config))
        with patch('export_engine.run_export', side_effect=fixture.renderer):
            produced = production_lifecycle.produce(fixture.root)
        core = lifecycle.Lifecycle(fixture.root, fixture.config)
        approval = core.approve_design(produced['candidate_id'], produced['validation']['id'], 'owner', 'fixture:approval')
        delivery = core.seal(produced['candidate_id'], produced['validation']['id'], approval['id'])
        package = Path(delivery['local_path']); manifest_path = package / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        index_path = package / 'recipe/inputs' / SNAPSHOT_INDEX
        original = json.loads(index_path.read_text())
        self.assertTrue(any(item['path'].startswith('evidence/render/') for item in manifest['files']))
        self.assertFalse(any(item['path'].startswith('media/') and item['path'].endswith('.json') for item in manifest['files']))
        for mapping in ({}, {**original, 'api/inputs/fake/capture.png': '0' * 64}, {key: '0' * 64 for key in original}):
            with self.subTest(mapping=mapping):
                index_path.write_text(json.dumps(mapping))
                changed = copy.deepcopy(manifest)
                record = next(item for item in changed['files'] if item['path'] == index_path.relative_to(package).as_posix())
                record.update(sha256=lifecycle.digest(index_path), size_bytes=index_path.stat().st_size)
                manifest_path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'snapshot index'):
                    verify_archive(package)
                from delivery_lifecycle import restore_archive
                destination = fixture.root / 'restore-targets' / 'restored'
                with self.assertRaisesRegex(ValueError, 'snapshot index'):
                    restore_archive(package, destination, lifecycle.digest(manifest_path))
                self.assertFalse(destination.parent.exists())


class ArchiveApprovalBindingTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_approval_semantics_cannot_be_replaced_by_updated_file_hashes(self):
        import artifact_lifecycle as lifecycle
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        package = Path(delivery['local_path']); manifest_path = package / 'manifest.json'
        original = json.loads(manifest_path.read_text())
        mutations = [('validation', {'status': 'FAIL'}), ('validation', {'candidate_id': 'other'}),
                     ('validation', {'run_id': 'other'}), ('design-approval', {'stage': 'upload'}),
                     ('design-approval', {'actor': '  '}), ('design-approval', {'authorization_reference': ''}),
                     ('design-approval', {'validation_id': 'other'}), ('design-approval', {'config_sha256': '0'*64})]
        for name, change in mutations:
            with self.subTest(name=name, change=change):
                evidence = package / 'evidence' / (name + '.json')
                saved = evidence.read_bytes()
                evidence.write_text(json.dumps({**json.loads(saved), **change}))
                changed = copy.deepcopy(original)
                entry = next(item for item in changed['files'] if item['path'] == evidence.relative_to(package).as_posix())
                entry.update(sha256=lifecycle.digest(evidence), size_bytes=evidence.stat().st_size)
                manifest_path.write_text(json.dumps(changed))
                try:
                    with self.assertRaisesRegex(ValueError, 'approval|validation'):
                        verify_archive(package)
                finally:
                    evidence.write_bytes(saved)
                    manifest_path.write_text(json.dumps(original))
