"""Open incidents retain evidence until an explicit immutable resolution."""
import unittest
import test_artifact_lifecycle as fixtures


class IncidentTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def trial(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'input'; source.write_bytes(b'source')
        dependency = self.store.register(attempt['id'], source, 'source')
        source.write_bytes(b'rendered')
        artifact = self.store.register(attempt['id'], source, 'screenshot', inputs=[dependency['id']])
        self.store.finish_attempt(attempt['id'], 'failed', reason='Wrong poster')
        return artifact, dependency

    def test_incident_protects_artifact_and_recursive_dependencies(self):
        artifact, _ = self.trial()
        incident = self.store.open_incident(actor='owner', reason='Poster investigation', artifacts=[artifact['id']])
        self.assertEqual(self.store.plan_cleanup(retention_days=0)['objects'], [])
        self.assertEqual(self.store.incident_status(incident['id'])['status'], 'open')
        self.store.close_incident(incident['id'], actor='owner', resolution='Reproduced and replaced')
        self.assertEqual(len(self.store.plan_cleanup(retention_days=0)['objects']), 2)
        with self.assertRaisesRegex(ValueError, 'Immutable'):
            self.store.close_incident(incident['id'], actor='owner', resolution='Rewrite')

    def test_incident_can_protect_quarantined_bytes_and_invalidate_purge(self):
        artifact, _ = self.trial()
        cleanup = self.store.plan_cleanup(retention_days=0)
        operation = self.store.quarantine_cleanup(cleanup['id'], actor='owner', reason='Rejected')
        plan = self.store.plan_purge(operation['id'], quarantine_days=0)
        self.store.open_incident(actor='owner', reason='Need original evidence', artifacts=[artifact['id']])
        with self.assertRaisesRegex(ValueError, 'protected|stale'):
            self.store.purge_cleanup(plan['id'], actor='owner', reason='Expired')
        self.store.restore_cleanup(operation['id'], actor='owner', reason='Investigate')
        self.store.verify_artifact(artifact['id'])

    def test_invalid_reference_and_empty_reason_do_not_create_incidents(self):
        for arguments in ({'actor': 'owner', 'reason': '', 'artifacts': ['missing']},
                          {'actor': 'owner', 'reason': 'Investigate', 'artifacts': ['missing']},
                          {'actor': 'owner', 'reason': 'Investigate'}):
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.store.open_incident(**arguments)
        self.assertEqual(list((self.store.paths.workspace / 'records/incidents').glob('*.json')), [])

    def test_discarded_candidate_is_protected_by_open_incident(self):
        artifact, _ = self.trial()
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'candidate'; source.write_bytes(b'candidate')
        selected = self.store.register(attempt['id'], source, 'screenshot', inputs=[artifact['id']])
        self.store.finish_attempt(attempt['id'], 'succeeded')
        candidate = self.store.select(run['id'], [selected['id']])
        self.store.discard_candidate(candidate['id'], actor='owner', reason='Investigating')
        incident = self.store.open_incident(actor='owner', reason='Evidence review', candidates=[candidate['id']])
        self.assertEqual(self.store.plan_cleanup(retention_days=0)['objects'], [])
        self.store.close_incident(incident['id'], actor='owner', resolution='Resolved')
        self.assertEqual(len(self.store.plan_cleanup(retention_days=0)['objects']), 3)

    def test_cli_opens_and_closes_same_incident(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        artifact, _ = self.trial()
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        command = [sys.executable, str(cli), 'incident']
        opened = subprocess.run(command + ['open', '--repo', str(self.root), '--actor', 'owner',
            '--reason', 'Investigate', '--artifact', artifact['id']], capture_output=True, text=True)
        self.assertEqual(opened.returncode, 0, opened.stderr)
        identity = json.loads(opened.stdout)['id']
        closed = subprocess.run(command + ['close', '--repo', str(self.root), '--id', identity,
            '--actor', 'owner', '--resolution', 'Resolved', '--confirm', 'CLOSE'], capture_output=True, text=True)
        self.assertEqual(closed.returncode, 0, closed.stderr)
        self.assertEqual(self.store.incident_status(identity)['status'], 'closed')
