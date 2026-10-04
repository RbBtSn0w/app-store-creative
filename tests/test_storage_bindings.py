"""Immutable move evidence is required to resolve historical storage locations."""
import copy
import hashlib
from pathlib import Path
import unittest
import test_artifact_lifecycle as fixtures
from artifact_lifecycle import canonical


class StorageBindingTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def edge(self, source, destination, identity='move'):
        key = hashlib.sha256(canonical(source)).hexdigest()
        switched = self.store._record('relocations', {'id': identity, 'status': 'SWITCHED',
            'from': source, 'to': destination, 'config_path': str(self.store.config_path),
            'project_id': self.cfg['project']['id']}, 'switched')
        self.store._record('storage-bindings', {'id': key, 'from': source, 'to': destination,
            'relocation_id': identity, 'switch_sha256': hashlib.sha256(canonical(switched)).hexdigest()})

    def test_verified_chain_resolves_old_run_without_modifying_record(self):
        run = self.store.start_run({}); path = self.store._path('runs', run['id']); before = path.read_bytes()
        historical = copy.deepcopy(run['storage']); historical['objects'] = str(self.root / 'old objects')
        self.edge(historical, self.store.paths.binding())
        self.assertEqual(self.store.resolve_storage_binding(historical), self.store.paths.binding())
        self.assertEqual(path.read_bytes(), before)

    def test_missing_switch_evidence_is_rejected(self):
        old = copy.deepcopy(self.store.paths.binding()); old['objects'] = str(self.root / 'old objects')
        self.edge(old, self.store.paths.binding())
        self.store._path('relocations', 'move', 'switched').unlink()
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.resolve_storage_binding(old)

    def test_tampered_binding_cannot_redirect_to_another_location(self):
        old = copy.deepcopy(self.store.paths.binding()); old['objects'] = str(self.root / 'old objects')
        self.edge(old, self.store.paths.binding())
        key = hashlib.sha256(canonical(old)).hexdigest()
        import json
        path = self.store._path('storage-bindings', key); record = json.loads(path.read_text())
        record['to']['objects'] = str(self.root / 'private'); path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.resolve_storage_binding(old)

    def test_cycle_is_rejected(self):
        current = self.store.paths.binding(); first = {**current, 'objects': str(self.root / 'first')}
        second = {**current, 'objects': str(self.root / 'second')}
        self.edge(first, second, 'first'); self.edge(second, first, 'second')
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.store.resolve_storage_binding(first)

    def test_two_moves_resolve_historical_run_without_rewriting_it(self):
        run = self.store.start_run({}); current = self.store.paths.binding()
        first = {**current, 'objects': str(self.root / 'first')}
        second = {**current, 'objects': str(self.root / 'second')}
        historical = {key: value for key, value in run.items() if key not in ('schema_version', 'created_at')}
        historical.update(id='historical-run', storage=first)
        self.store._record('runs', historical)
        path = self.store._path('runs', 'historical-run'); before = path.read_bytes()
        self.edge(first, second, 'first'); self.edge(second, current, 'second')
        self.assertEqual(self.store._run('historical-run')['storage'], first)
        self.assertEqual(path.read_bytes(), before)

    def test_other_configuration_authority_cannot_use_move_evidence(self):
        from artifact_lifecycle import Lifecycle
        current = self.store.paths.binding(); old = {**current, 'objects': str(self.root / 'old')}
        self.edge(old, current)
        other = Lifecycle(self.root, self.cfg, self.root / 'other.config.json')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            other.resolve_storage_binding(old)
