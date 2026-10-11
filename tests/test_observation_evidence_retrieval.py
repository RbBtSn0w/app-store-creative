"""Portable observation evidence restoration fails closed without a project database."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_artifact_lifecycle
from external_media_store import FileSystemMediaStore
from remote_observations import retrieve_observation_evidence


class ObservationEvidenceRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.backend = self.root / 'private'
        self.source = self.root / 'original.bin'
        self.source.write_bytes(b'original private executor receipt')
        self.store = FileSystemMediaStore('evidence', self.backend)
        self.reference = self.store.persist(self.source)
        self.locator = {'schema_version': 1, 'id': '1' * 32, 'observation_id': '2' * 32,
            'publication_id': '3' * 32, 'plan_sha256': '4' * 64,
            'evidence_sha256': self.reference['sha256'], 'reference': self.reference}
        from artifact_lifecycle import canonical
        summary = {'schema_version': 1, 'id': '2' * 32, 'observation_id': '2' * 32,
            'publication_id': '3' * 32, 'plan_sha256': '4' * 64, 'artifact_id': '5' * 32,
            'gate': 'processing', 'source': 'asc-api', 'observed_at': '2026-10-09T00:00:00+00:00',
            'evidence_sha256': self.reference['sha256'], 'facts': {'processing_state': 'COMPLETE'}}
        self.locator.update(summary=summary, summary_sha256=hashlib.sha256(canonical(summary)).hexdigest())
        self.path = self.root / 'locator.json'
        self.destination = self.root / 'restored.bin'

    def write(self, locator=None):
        self.path.write_text(json.dumps(self.locator if locator is None else locator))
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def retrieve(self, expected):
        return retrieve_observation_evidence(self.path, expected, self.backend, self.destination)

    def test_wrong_trusted_locator_hash_creates_no_output(self):
        self.write()
        with self.assertRaisesRegex(ValueError, 'trusted hash'):
            self.retrieve('0' * 64)
        self.assertFalse(self.destination.exists())

    def test_unknown_schema_and_private_fields_are_refused(self):
        for change in ({'schema_version': True}, {'schema_version': 2},
                       {'private_root': str(self.root)}, {'id': '../outside'},
                       {'evidence_sha256': '0' * 64}):
            with self.subTest(change=change):
                expected = self.write({**self.locator, **change})
                with self.assertRaisesRegex(ValueError, 'locator'):
                    self.retrieve(expected)
                self.assertFalse(self.destination.exists())

    def test_summary_hash_scope_and_private_fields_are_refused_before_retrieval(self):
        from artifact_lifecycle import canonical
        for change in ({'publication_id': '9' * 32}, {'private_path': str(self.root)}):
            with self.subTest(change=change):
                summary = {**self.locator['summary'], **change}
                locator = {**self.locator, 'summary': summary,
                    'summary_sha256': hashlib.sha256(canonical(summary)).hexdigest()}
                with self.assertRaisesRegex(ValueError, 'summary'):
                    self.retrieve(self.write(locator))
                self.assertFalse(self.destination.exists())
        locator = {**self.locator, 'summary_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'summary'):
            self.retrieve(self.write(locator))
        self.assertFalse(self.destination.exists())

    def test_summary_rejects_sensitive_values_even_with_matching_hash(self):
        from artifact_lifecycle import canonical
        for change in ({'artifact_id': '/private/local/path'}, {'observed_at': 'secret-token'},
                       {'facts': {'processing_state': 'https://private.example/token'}},
                       {'gate': []}, {'source': []}):
            with self.subTest(change=change):
                summary = {**self.locator['summary'], **change}
                locator = {**self.locator, 'summary': summary,
                    'summary_sha256': hashlib.sha256(canonical(summary)).hexdigest()}
                with self.assertRaises(ValueError):
                    self.retrieve(self.write(locator))
                self.assertFalse(self.destination.exists())

    def test_damaged_backend_bytes_are_refused_without_output(self):
        expected = self.write()
        self.store.object_path(self.reference).write_bytes(b'changed receipt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.retrieve(expected)
        self.assertFalse(self.destination.exists())

    def test_existing_destination_is_preserved(self):
        expected = self.write()
        self.destination.write_bytes(b'existing user file')
        with self.assertRaises(ValueError):
            self.retrieve(expected)
        self.assertEqual(self.destination.read_bytes(), b'existing user file')

    def test_missing_backend_version_creates_no_output(self):
        expected = self.write()
        self.store.object_path(self.reference).unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.retrieve(expected)
        self.assertFalse(self.destination.exists())
