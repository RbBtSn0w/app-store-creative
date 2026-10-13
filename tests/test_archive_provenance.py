"""Sealed packages preserve and verify the complete artifact dependency graph."""
import copy
import json
from pathlib import Path
import unittest
import test_delivery_lifecycle as fixtures
import artifact_lifecycle as lifecycle
from delivery_lifecycle import verify_archive


class ArchiveProvenanceTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def test_source_graph_is_portable_and_rejects_incomplete_or_failed_producers(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        package = Path(delivery['local_path']); graph_path = package / 'evidence/provenance.json'
        graph = json.loads(graph_path.read_text())
        self.assertEqual(graph['roots'], [self.output['id']])
        nodes = {node['id']: node for node in graph['nodes']}
        self.assertEqual(nodes[self.output['id']]['inputs'], [self.input['id']])
        self.assertEqual(nodes[self.input['id']]['inputs'], [])
        self.assertTrue(verify_archive(package)['provenance_verified'])
        manifest_path = package / 'manifest.json'; manifest = json.loads(manifest_path.read_text())
        mutations = []
        changed = copy.deepcopy(graph); changed['nodes'].pop(0); mutations.append(changed)
        changed = copy.deepcopy(graph); changed['nodes'][0]['inputs'] = [self.output['id']]; mutations.append(changed)
        changed = copy.deepcopy(graph); changed['nodes'][0]['producer_status'] = 'failed'; mutations.append(changed)
        changed = copy.deepcopy(graph); changed['nodes'][0]['sha256'] = '0'*64; mutations.append(changed)
        for index, changed in enumerate(mutations):
            with self.subTest(case=index):
                graph_path.write_text(json.dumps(changed)); modified = copy.deepcopy(manifest)
                entry = next(item for item in modified['files'] if item['path'] == 'evidence/provenance.json')
                entry.update(sha256=lifecycle.digest(graph_path), size_bytes=graph_path.stat().st_size)
                manifest_path.write_text(json.dumps(modified))
                with self.assertRaisesRegex(ValueError, 'provenance'):
                    verify_archive(package)

    def test_long_dependency_chain_is_verified_without_python_recursion(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        package = Path(delivery['local_path']); graph_path = package / 'evidence/provenance.json'
        graph = json.loads(graph_path.read_text()); manifest_path = package / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        source = next(node for node in graph['nodes'] if node['id'] == self.input['id'])
        output = next(node for node in graph['nodes'] if node['id'] == self.output['id'])
        count = 1200
        output['inputs'] = ['chain-0']
        for index in range(count):
            node = {**source, 'id': 'chain-' + str(index),
                    'inputs': ['chain-' + str(index + 1)] if index + 1 < count else [source['id']]}
            graph['nodes'].append(node)
            manifest['recipe_inputs'].append({'artifact_id': node['id'], 'path': node['path'], 'sha256': node['sha256']})
        graph_path.write_text(json.dumps(graph))
        entry = next(item for item in manifest['files'] if item['path'] == 'evidence/provenance.json')
        entry.update(sha256=lifecycle.digest(graph_path), size_bytes=graph_path.stat().st_size)
        manifest_path.write_text(json.dumps(manifest))
        self.assertTrue(verify_archive(package)['provenance_verified'])

    def test_core_closure_uses_same_unbounded_depth_contract(self):
        from unittest.mock import patch
        nodes = {'node-' + str(index): {'id': 'node-' + str(index),
                 'inputs': ['node-' + str(index + 1)] if index < 1199 else []} for index in range(1200)}
        with patch.object(self.store, 'verify_artifact', side_effect=lambda identity: nodes[identity]):
            self.assertEqual(set(self.store._closure(['node-0'])), set(nodes))
