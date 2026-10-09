"""Remote completion derives from separately bound, nonconflicting evidence."""
from datetime import datetime, timezone
import hashlib
import unittest
import test_publication_lifecycle as fixtures
from artifact_lifecycle import canonical


class RemoteObservationTests(unittest.TestCase):
    setUp = fixtures.PublicationLifecycleTests.setUp
    git = fixtures.PublicationLifecycleTests.git
    persist = fixtures.PublicationLifecycleTests.persist

    def plan(self, approved=True):
        plan = self.store.plan_publication(self.delivery['id'], self.persist(), self.target)
        if approved:
            self.store.approve_upload(plan['id'], 'owner', 'human:upload')
        return plan

    def observe(self, plan, gate, facts, **extra):
        return self.store.record_observation(plan['id'], {
            'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': self.target,
            'artifact_id': plan['assets'][0]['artifact_id'], 'remote_id': 'remote-media',
            'gate': gate, 'source': 'asc-api' if gate in ('upload', 'processing') else 'media-probe',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'evidence_reference': 'executor:verified-receipt',
            'evidence_sha256': hashlib.sha256(canonical(facts)).hexdigest(),
            'facts': facts, **extra}, canonical(facts))

    def test_observation_requires_matching_evidence_bytes(self):
        plan = self.plan()
        observation = {
            'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': self.target,
            'artifact_id': plan['assets'][0]['artifact_id'], 'remote_id': 'remote-media',
            'gate': 'processing', 'source': 'asc-api',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'evidence_reference': 'executor:receipt', 'facts': {'processing_state': 'COMPLETE'},
            'evidence_sha256': hashlib.sha256(b'original evidence').hexdigest()}
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.record_observation(plan['id'], observation, b'changed evidence')
        for invalid in ('', 'A' * 64, True):
            with self.subTest(evidence_sha256=invalid), self.assertRaisesRegex(ValueError, 'evidence'):
                self.store.record_observation(plan['id'], {**observation, 'evidence_sha256': invalid}, b'original evidence')
        missing = dict(observation); missing.pop('evidence_sha256')
        with self.assertRaisesRegex(ValueError, 'fields'):
            self.store.record_observation(plan['id'], missing, b'original evidence')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.record_observation(plan['id'], observation, b'')
        self.assertEqual(list((self.store.paths.workspace / 'records/remote-observations').glob('*.json')), [])

    def test_missing_saved_evidence_hash_is_not_accepted_as_history(self):
        import json
        plan = self.plan()
        saved = self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        path = self.store._path('remote-observations', saved['id'])
        saved.pop('evidence_sha256')
        path.write_text(json.dumps(saved))
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.publication_status(plan['id'])
        self.assertEqual(path.read_bytes(), before)

    def test_changed_observation_facts_cannot_become_remote_success(self):
        import json
        plan = self.plan()
        saved = self.observe(plan, 'processing', {'processing_state': 'FAILED'})
        path = self.store._path('remote-observations', saved['id'])
        saved['facts']['processing_state'] = 'COMPLETE'
        path.write_text(json.dumps(saved))
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.store.publication_status(plan['id'])
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.store.export_publication(plan['id'], write=True)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.store.paths.publications / plan['id'] / 'plan.json').exists())

    def test_upload_receipt_alone_never_proves_media_completion(self):
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_separate_matching_observations_prove_screenshot_completion(self):
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        self.observe(plan, 'media', {'media_verified': True})
        state = self.store.publication_status(plan['id'])
        self.assertEqual(state['status'], 'PASS')
        self.assertTrue(state['remote_verified'])
        self.assertFalse(state['remote_write'])

    def test_conflicting_observations_require_explicit_supersession(self):
        plan = self.plan()
        first = self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        second = self.observe(plan, 'processing', {'processing_state': 'FAILED'})
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'CONFLICT')
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, supersedes=[first['id'], second['id']])
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'UNKNOWN')

    def test_foreign_plan_and_target_observations_are_rejected(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, plan_sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'scope'):
            self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, target={**self.target, 'app_id': 'foreign'})

    def test_unapproved_remote_facts_cannot_mark_completion(self):
        plan = self.plan(approved=False)
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        self.observe(plan, 'media', {'media_verified': True})
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_sensitive_or_unrecognized_receipt_fields_are_rejected(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, 'facts'):
            self.observe(plan, 'processing', {'processing_state': 'COMPLETE', 'authorization': 'secret'})

    def test_stale_observations_never_prove_completion(self):
        from datetime import timedelta
        plan = self.plan()
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']}, observed_at=old)
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, observed_at=old)
        self.observe(plan, 'media', {'media_verified': True}, observed_at=old)
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'UNKNOWN')

    def test_different_remote_resources_are_conflicting(self):
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'}, remote_id='different-resource')
        self.assertEqual(self.store.publication_status(plan['id'])['status'], 'CONFLICT')

    def test_preview_requires_decoded_poster_and_playback(self):
        from remote_observations import gate_result, requirements
        preview = {'role': 'preview', 'poster_frame_time_code': '00:00:05:01'}
        self.assertEqual(requirements(preview), ['upload', 'processing', 'playback', 'poster'])
        facts = {'poster_width': 1920, 'poster_height': 1080, 'poster_frame_time_code': '00:00:05:01'}
        self.assertEqual(gate_result(preview, 'poster', facts, 'asc-api'), 'UNKNOWN')
        self.assertEqual(gate_result(preview, 'poster', {**facts, 'poster_verified': True}, 'media-probe'), 'PASS')
        self.assertEqual(gate_result(preview, 'poster', {**facts, 'poster_verified': False}, 'browser'), 'FAIL')

    def test_corrupted_archive_prevents_complete_publication(self):
        from pathlib import Path
        plan = self.plan()
        self.observe(plan, 'upload', {'found': True, 'source_checksum': plan['assets'][0]['source_checksum']})
        self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        self.observe(plan, 'media', {'media_verified': True})
        (Path(self.delivery['local_path']) / 'media/en-US/mac_16_10/hero.png').write_bytes(b'corrupt')
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_export_preserves_sanitized_observations_without_overwrite(self):
        import json
        from pathlib import Path
        plan = self.plan()
        observation = self.observe(plan, 'processing', {'processing_state': 'COMPLETE'})
        exported = self.store.export_publication(plan['id'], write=True)
        path = Path(exported['handoff_path']).parent / 'observations' / (observation['id'] + '.json')
        self.assertEqual(json.loads(path.read_text())['id'], observation['id'])
        self.assertNotIn(str(self.root), path.read_text())
        before = path.read_bytes()
        self.store.export_publication(plan['id'], write=True)
        self.assertEqual(path.read_bytes(), before)

    def test_cli_imports_executor_observation_into_shared_status(self):
        import json
        from pathlib import Path
        import subprocess
        import sys
        plan = self.plan()
        observation = {'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': self.target,
            'artifact_id': plan['assets'][0]['artifact_id'], 'remote_id': 'media', 'gate': 'processing',
            'source': 'asc-cli', 'observed_at': datetime.now(timezone.utc).isoformat(),
            'evidence_reference': 'asc:receipt-123', 'evidence_sha256': hashlib.sha256(b'executor evidence').hexdigest(),
            'facts': {'processing_state': 'COMPLETE'}}
        (self.root / 'evidence.txt').write_bytes(b'executor evidence')
        (self.root / 'receipt.json').write_text(json.dumps(observation))
        (self.root / 'creative.config.json').write_text(json.dumps(self.config))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'observe', '--repo', str(self.root),
            '--id', plan['id'], '--observation', 'receipt.json', '--evidence', 'evidence.txt'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.store.publication_status(plan['id'])
        self.assertEqual(next(g for g in state['gates'] if g['gate'] == 'processing')['status'], 'PASS')

    def test_retained_observation_evidence_is_managed_and_protected(self):
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        before = self.store._path('remote-observations', observation['id']).read_bytes()
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        artifact = self.store.verify_artifact(retained['artifact_id'])
        self.assertEqual(artifact['sha256'], observation['evidence_sha256'])
        self.assertEqual(artifact['role'], 'observation-evidence')
        self.assertEqual(self.store.object_path(artifact['sha256']).read_bytes(), canonical(facts))
        self.assertEqual(self.store._path('remote-observations', observation['id']).read_bytes(), before)
        cleanup = self.store.plan_cleanup(0)
        self.assertNotIn(artifact['sha256'], {item['sha256'] for item in cleanup['objects']})
        attempts = list((self.store.paths.workspace / 'records/attempts').glob('*/started.json'))
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.store.retain_observation_evidence(observation['id'], b'changed', 'fixture-owner')
        self.assertEqual(list((self.store.paths.workspace / 'records/attempts').glob('*/started.json')), attempts)

    def test_private_raw_receipt_is_not_copied_into_git_summary(self):
        plan = self.plan()
        raw = b'{"token":"fixture-sensitive-token","path":"/private/fixture","processing":"COMPLETE"}'
        observation = self.store.record_observation(plan['id'], {
            'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': self.target,
            'artifact_id': plan['assets'][0]['artifact_id'], 'remote_id': 'remote-media',
            'gate': 'processing', 'source': 'asc-api',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'evidence_reference': 'executor:receipt', 'facts': {'processing_state': 'COMPLETE'},
            'evidence_sha256': hashlib.sha256(raw).hexdigest()}, raw)
        retained = self.store.retain_observation_evidence(observation['id'], raw, 'fixture-owner')
        self.store.persist_observation_evidence(retained['id'], 'evidence-team', self.root / 'private-backend')
        self.store.export_publication(plan['id'], write=True)
        for path in (self.store.paths.publications / plan['id']).rglob('*'):
            if path.is_file():
                self.assertNotIn(b'fixture-sensitive-token', path.read_bytes())
                self.assertNotIn(b'/private/fixture', path.read_bytes())
        artifact = self.store.verify_artifact(retained['artifact_id'])
        self.assertEqual(self.store.object_path(artifact['sha256']).read_bytes(), raw)

    def test_legitimately_committed_missing_or_crossed_summary_binding_is_rejected(self):
        from artifact_lifecycle import identifier
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        first = self.observe(plan, 'processing', facts)
        second = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(first['id'], canonical(facts), 'owner')
        other = self.store.retain_observation_evidence(second['id'], canonical(facts), 'owner')
        for missing in ('summary_artifact_id', 'summary_sha256'):
            data = {key: value for key, value in retained.items()
                    if key not in ('schema_version', 'created_at', '_commit_event_id', missing)}
            data['id'] = identifier()
            committed = self.store._record('observation-evidence', data)
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'summary'):
                self.store.persist_observation_evidence(committed['id'], 'evidence', self.root / 'backend')
        data = {key: value for key, value in retained.items()
                if key not in ('schema_version', 'created_at', '_commit_event_id')}
        data.update(id=identifier(), summary_artifact_id=other['summary_artifact_id'],
                    summary_sha256=other['summary_sha256'])
        committed = self.store._record('observation-evidence', data)
        with self.assertRaisesRegex(ValueError, 'summary'):
            self.store.persist_observation_evidence(committed['id'], 'evidence', self.root / 'backend')
        self.assertFalse((self.root / 'backend').exists())

    def evidence_relocation_crash_case(self, action, stage='configuration', reverse=False):
        import json
        from artifact_lifecycle import Lifecycle
        from test_relocation_process_crash import RelocationProcessCrashTests
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        original = self.store._path('observation-evidence', retained['id']).read_bytes()
        self.store.config_path.write_text(json.dumps(self.config))
        relocation = self.store.plan_relocation({'workspaceRoot': 'crash working',
            'objectRoot': 'crash objects', 'releaseRoot': 'crash releases', 'publicationRoot': 'crash publications'})
        policy = self.store.relocation_git_policy(relocation['id'])
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        self.store.prepare_relocation(relocation['id'], 'owner', 'Crash evidence fixture')
        core = self.store
        if reverse:
            core.switch_relocation(relocation['id'], 'owner', 'Move before reverse crash')
            core = Lifecycle.from_configuration(self.root, core.config_path)
            relocation = core.plan_reverse_relocation(relocation['id'])
            policy = core.relocation_git_policy(relocation['id'])
            rules = self.root / '.gitignore'
            rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
            core.prepare_reverse_relocation(relocation['id'], 'owner', 'Reverse crash fixture')
        RelocationProcessCrashTests.crash(self, core, relocation, reverse=reverse, stage=stage)
        result = RelocationProcessCrashTests.recover(self, core, relocation, action, reverse=reverse)
        self.assertEqual(result['status'], 'SWITCHED' if action == 'resume' else 'ROLLED_BACK')
        active = Lifecycle.from_configuration(self.root, self.store.config_path)
        self.assertEqual(active._path('observation-evidence', retained['id']).read_bytes(), original)
        active.verify_artifact(retained['artifact_id'])
        active._verify_observation_summary(active._read('observation-evidence', retained['id']),
            active._read('remote-observations', observation['id']))
        saved = active.persist_observation_evidence(retained['id'], 'evidence', self.root / 'private-backend')
        self.assertTrue(saved['retrieval_verified'])

    def test_evidence_relocation_sigkill_resumes_through_public_cli(self):
        self.evidence_relocation_crash_case('resume')

    def test_evidence_relocation_sigkill_rolls_back_through_public_cli(self):
        self.evidence_relocation_crash_case('rollback')

    def test_evidence_relocation_directory_sigkill_resumes_through_public_cli(self):
        self.evidence_relocation_crash_case('resume', stage='directory')

    def test_evidence_relocation_directory_sigkill_rolls_back_through_public_cli(self):
        self.evidence_relocation_crash_case('rollback', stage='directory')

    def test_reverse_evidence_relocation_configuration_sigkill_resumes(self):
        self.evidence_relocation_crash_case('resume', reverse=True)

    def test_reverse_evidence_relocation_configuration_sigkill_rolls_back(self):
        self.evidence_relocation_crash_case('rollback', reverse=True)

    def test_reverse_evidence_relocation_directory_sigkill_resumes(self):
        self.evidence_relocation_crash_case('resume', stage='directory', reverse=True)

    def test_reverse_evidence_relocation_directory_sigkill_rolls_back(self):
        self.evidence_relocation_crash_case('rollback', stage='directory', reverse=True)

    def test_evidence_forward_intent_sigkill_resume(self):
        self.evidence_relocation_crash_case('resume', stage='intent', reverse=False)

    def test_evidence_forward_intent_sigkill_rollback(self):
        self.evidence_relocation_crash_case('rollback', stage='intent', reverse=False)

    def test_evidence_forward_receipt_sigkill_resume(self):
        self.evidence_relocation_crash_case('resume', stage='receipt', reverse=False)

    def test_evidence_forward_receipt_sigkill_rollback(self):
        self.evidence_relocation_crash_case('rollback', stage='receipt', reverse=False)

    def test_evidence_reverse_intent_sigkill_resume(self):
        self.evidence_relocation_crash_case('resume', stage='intent', reverse=True)

    def test_evidence_reverse_intent_sigkill_rollback(self):
        self.evidence_relocation_crash_case('rollback', stage='intent', reverse=True)

    def test_evidence_reverse_receipt_sigkill_resume(self):
        self.evidence_relocation_crash_case('resume', stage='receipt', reverse=True)

    def test_evidence_reverse_receipt_sigkill_rollback(self):
        self.evidence_relocation_crash_case('rollback', stage='receipt', reverse=True)

    def test_evidence_and_summary_survive_four_root_relocation(self):
        import json
        from artifact_lifecycle import Lifecycle
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        identities = [retained['artifact_id'], retained['summary_artifact_id']]
        before = {identity: self.store._path('artifacts', identity).read_bytes() for identity in identities}
        self.store.config_path.write_text(json.dumps(self.config))
        relocation = self.store.plan_relocation({'workspaceRoot': 'moved working',
            'objectRoot': 'moved objects', 'releaseRoot': 'moved releases', 'publicationRoot': 'moved publications'})
        policy = self.store.relocation_git_policy(relocation['id'])
        (self.root / '.gitignore').write_text('\n'.join(policy['gitignore']) + '\n')
        self.store.prepare_relocation(relocation['id'], 'owner', 'Evidence relocation fixture')
        self.store.switch_relocation(relocation['id'], 'owner', 'Evidence relocation fixture')
        moved = Lifecycle.from_configuration(self.root, self.store.config_path)
        for identity in identities:
            moved.verify_artifact(identity)
            self.assertEqual(moved._path('artifacts', identity).read_bytes(), before[identity])
        moved._verify_observation_summary(moved._read('observation-evidence', retained['id']),
            moved._read('remote-observations', observation['id']))
        saved = moved.persist_observation_evidence(retained['id'], 'evidence', self.root / 'private-backend')
        self.assertTrue(saved['retrieval_verified'])
        reverse = moved.plan_reverse_relocation(relocation['id'])
        policy = moved.relocation_git_policy(reverse['id'])
        rules = self.root / '.gitignore'
        rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
        moved.prepare_reverse_relocation(reverse['id'], 'owner', 'Return evidence fixture')
        moved.switch_reverse_relocation(reverse['id'], 'owner', 'Return evidence fixture')
        returned = Lifecycle.from_configuration(self.root, moved.config_path)
        for identity in identities:
            returned.verify_artifact(identity)
            self.assertEqual(returned._path('artifacts', identity).read_bytes(), before[identity])
        returned._verify_observation_summary(returned._read('observation-evidence', retained['id']),
            returned._read('remote-observations', observation['id']))
        cleanup = returned.plan_cleanup(0)
        protected = {returned.verify_artifact(identity)['sha256'] for identity in identities}
        self.assertFalse(protected & {item['sha256'] for item in cleanup['objects']})
        repeated = returned.plan_relocation({'workspaceRoot': 'third working',
            'objectRoot': 'third objects', 'releaseRoot': 'third releases', 'publicationRoot': 'third publications'})
        policy = returned.relocation_git_policy(repeated['id'])
        rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
        returned.prepare_relocation(repeated['id'], 'owner', 'Repeat evidence fixture')
        returned.switch_relocation(repeated['id'], 'owner', 'Repeat evidence fixture')
        third = Lifecycle.from_configuration(self.root, returned.config_path)
        reverse_again = third.plan_reverse_relocation(repeated['id'])
        policy = third.relocation_git_policy(reverse_again['id'])
        rules.write_text(rules.read_text() + '\n'.join(policy['gitignore']) + '\n')
        third.prepare_reverse_relocation(reverse_again['id'], 'owner', 'Return repeated evidence fixture')
        third.switch_reverse_relocation(reverse_again['id'], 'owner', 'Return repeated evidence fixture')
        final = Lifecycle.from_configuration(self.root, third.config_path)
        for identity in identities:
            final.verify_artifact(identity)
            self.assertEqual(final._path('artifacts', identity).read_bytes(), before[identity])
        exported = final._observation_evidence_exports(plan['id'], observation['plan_sha256'])
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]['reference'], saved['reference'])
        self.assertEqual(exported[0]['summary_sha256'], retained['summary_sha256'])

    def test_quarantine_restore_preserves_referenced_raw_and_summary(self):
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        identities = [retained['artifact_id'], retained['summary_artifact_id']]
        preserved = {identity: self.store._path('artifacts', identity).read_bytes() for identity in identities}
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'diagnostic', 'owner')
        source = self.store.work_path(attempt['id']) / 'failed.bin'
        source.write_bytes(b'Disposable failed capture fixture')
        disposable = self.store.register(attempt['id'], source, 'source')
        self.store.finish_attempt(attempt['id'], 'failed', reason='Disposable fixture')
        cleanup = self.store.plan_cleanup(0)
        selected = {item['sha256'] for item in cleanup['objects']}
        self.assertIn(disposable['sha256'], selected)
        self.assertFalse({self.store.verify_artifact(i)['sha256'] for i in identities} & selected)
        operation = self.store.quarantine_cleanup(cleanup['id'], 'owner', 'Quarantine fixture')
        self.assertFalse(self.store.object_path(disposable['sha256']).exists())
        for identity in identities:
            self.store.verify_artifact(identity)
            self.assertEqual(self.store._path('artifacts', identity).read_bytes(), preserved[identity])
        self.store.restore_cleanup(operation['id'], 'owner', 'Restore fixture')
        self.store.verify_artifact(disposable['id'])
        second_plan = self.store.plan_cleanup(0)
        second_operation = self.store.quarantine_cleanup(second_plan['id'], 'owner', 'Disposable purge fixture')
        purge_plan = self.store.plan_purge(second_operation['id'], quarantine_days=0)
        self.store.purge_cleanup(purge_plan['id'], 'owner', 'Purge disposable fixture only')
        self.assertFalse(self.store.object_path(disposable['sha256']).exists())
        self.assertFalse(self.store._quarantine_path(second_operation['id'], disposable['sha256']).exists())
        for identity in identities:
            self.store.verify_artifact(identity)
            self.assertEqual(self.store._path('artifacts', identity).read_bytes(), preserved[identity])
        self.store._verify_observation_summary(self.store._read('observation-evidence', retained['id']),
            self.store._read('remote-observations', observation['id']))

    def evidence_purge_crash_case(self, stage):
        from test_object_purge_process_crash import ObjectPurgeProcessCrashTests
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        identities = [retained['artifact_id'], retained['summary_artifact_id']]
        before = {i: self.store._path('artifacts', i).read_bytes() for i in identities}
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'owner')
        source = self.store.work_path(attempt['id']) / 'disposable.bin'
        source.write_bytes(b'Disposable purge interruption fixture')
        disposable = self.store.register(attempt['id'], source, 'source')
        self.store.finish_attempt(attempt['id'], 'failed', reason='Disposable fixture')
        cleanup = self.store.plan_cleanup(0)
        operation = self.store.quarantine_cleanup(cleanup['id'], 'owner', 'Disposable fixture')
        self.cfg = self.config
        self.quarantined = lambda: (disposable, operation)
        ObjectPurgeProcessCrashTests.crash_case(self, stage)
        for identity in identities:
            self.store.verify_artifact(identity)
            self.assertEqual(self.store._path('artifacts', identity).read_bytes(), before[identity])
        self.store._verify_observation_summary(self.store._read('observation-evidence', retained['id']),
            self.store._read('remote-observations', observation['id']))

    def test_evidence_protection_after_purge_intent_sigkill(self):
        self.evidence_purge_crash_case('intent')

    def test_evidence_protection_after_purge_checkpoint_sigkill(self):
        self.evidence_purge_crash_case('checkpoint')

    def test_evidence_protection_after_purge_receipt_sigkill(self):
        self.evidence_purge_crash_case('receipt')

    def test_retention_registers_distinct_sanitized_summary_dependency(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        raw = self.store.verify_artifact(retained['artifact_id'])
        summary = self.store.verify_artifact(retained['summary_artifact_id'])
        self.assertEqual(summary['role'], 'observation-summary')
        self.assertEqual(summary['inputs'], [raw['id']])
        self.assertEqual(retained['summary_sha256'], summary['sha256'])
        self.assertNotEqual(raw['sha256'], summary['sha256'])
        data = json.loads(self.store.object_path(summary['sha256']).read_bytes())
        self.assertEqual(data['observation_id'], observation['id'])
        self.assertEqual(data['evidence_sha256'], raw['sha256'])
        self.assertEqual(data['facts'], facts)
        self.assertNotIn('actor', data)
        self.assertNotIn('evidence_reference', data)
        cleanup = self.store.plan_cleanup(0)
        self.assertNotIn(summary['sha256'], {item['sha256'] for item in cleanup['objects']})

    def test_changed_plan_refuses_evidence_retention_before_attempt(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        changed = {**plan, 'required_actions': ['Changed publication contract']}
        self.store._path('publications', plan['id'], 'plan').write_text(json.dumps(changed))
        before = list((self.store.paths.workspace / 'records/attempts').glob('*/started.json'))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        self.assertEqual(list((self.store.paths.workspace / 'records/attempts').glob('*/started.json')), before)

    def test_public_cli_retains_private_observation_evidence(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        self.store.config_path.write_text(json.dumps(self.config))
        source = self.root / 'receipt.json'
        source.write_bytes(canonical(facts))
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'retain-evidence',
            '--repo', str(self.root), '--observation-id', observation['id'],
            '--evidence', str(source), '--actor', 'fixture-owner'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record['observation_id'], observation['id'])
        self.assertEqual(self.store.verify_artifact(record['artifact_id'])['sha256'], observation['evidence_sha256'])
        self.assertFalse((self.store.paths.publications / plan['id']).exists())

    def test_retained_evidence_persists_to_independently_retrievable_version(self):
        from external_media_store import FileSystemMediaStore
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        backend = self.root / 'private-evidence-backend'
        saved = self.store.persist_observation_evidence(retained['id'], 'evidence-team', backend)
        self.assertEqual(saved['artifact_id'], retained['artifact_id'])
        self.assertTrue(saved['retrieval_verified'])
        self.assertEqual(saved['reference']['sha256'], observation['evidence_sha256'])
        self.assertNotIn(str(self.root), str(saved['reference']))
        destination = self.root / 'independent-evidence-copy'
        FileSystemMediaStore('evidence-team', backend).retrieve(saved['reference'], destination)
        self.assertEqual(destination.read_bytes(), canonical(facts))
        self.assertFalse((self.store.paths.publications / plan['id']).exists())

    def test_public_cli_persists_retained_evidence_to_exact_version(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        from external_media_store import FileSystemMediaStore
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        self.store.config_path.write_text(json.dumps(self.config))
        backend = self.root / 'cli-evidence-backend'
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'publication', 'persist-evidence',
            '--repo', str(self.root), '--evidence-id', retained['id'],
            '--backend', 'evidence-team', '--backend-root', str(backend)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(saved['artifact_id'], retained['artifact_id'])
        destination = self.root / 'cli-independent-evidence'
        FileSystemMediaStore('evidence-team', backend).retrieve(saved['reference'], destination)
        self.assertEqual(destination.read_bytes(), canonical(facts))
        self.assertNotIn(str(self.root), json.dumps(saved['reference']))

    def test_publication_exports_version_locator_without_raw_evidence(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        saved = self.store.persist_observation_evidence(retained['id'], 'evidence-team', self.root / 'private-backend')
        self.store.export_publication(plan['id'], write=True)
        path = self.store.paths.publications / plan['id'] / 'evidence' / (saved['id'] + '.json')
        exported = json.loads(path.read_bytes())
        self.assertEqual(exported['observation_id'], observation['id'])
        self.assertEqual(exported['reference'], saved['reference'])
        self.assertEqual(exported['evidence_sha256'], observation['evidence_sha256'])
        self.assertNotIn(str(self.root), path.read_text())
        self.assertEqual(exported['summary']['facts'], facts)
        self.assertEqual(exported['summary_sha256'], retained['summary_sha256'])
        self.assertNotEqual(exported['summary_sha256'], exported['evidence_sha256'])
        self.assertNotIn('actor', exported['summary'])
        self.assertNotIn('evidence_reference', exported['summary'])
        self.assertFalse(any(p.suffix == '.bin' for p in path.parent.rglob('*')))

    def test_invalid_evidence_locator_refuses_export_before_any_files(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        saved = self.store.persist_observation_evidence(retained['id'], 'evidence-team', self.root / 'private-backend')
        path = self.store._path('external-media', saved['id'])
        changes = ({'root': str(self.root)}, {'backend': '/private/backend'},
                   {'version': 'other'}, {'sha256': '0' * 64},
                   {'size_bytes': True}, {'schema_version': True}, {'provider': 'unknown'})
        for change in changes:
            with self.subTest(change=change):
                changed = json.loads(json.dumps(saved))
                changed['reference'].update(change)
                path.write_text(json.dumps(changed))
                before = path.read_bytes()
                with self.assertRaisesRegex(ValueError, 'commit event binding'):
                    self.store.export_publication(plan['id'], write=True)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((self.store.paths.publications / plan['id']).exists())

    def test_clean_cli_retrieves_exported_evidence_without_project_configuration(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        backend = self.root / 'private-backend'
        saved = self.store.persist_observation_evidence(retained['id'], 'evidence-team', backend)
        self.store.export_publication(plan['id'], write=True)
        locator = self.store.paths.publications / plan['id'] / 'evidence' / (saved['id'] + '.json')
        clean = self.root / 'clean-consumer'
        clean.mkdir()
        copied = clean / 'locator.json'
        copied.write_bytes(locator.read_bytes())
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'archive', 'retrieve-evidence',
            '--repo', str(clean), '--path', str(copied), '--expected-sha256', hashlib.sha256(copied.read_bytes()).hexdigest(),
            '--backend-root', str(backend), '--destination', str(clean / 'receipt.bin')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response['retrieved'])
        self.assertEqual(response['summary_sha256'], retained['summary_sha256'])
        self.assertEqual(response['summary']['observation_id'], observation['id'])
        self.assertEqual((clean / 'receipt.bin').read_bytes(), canonical(facts))
        self.assertEqual({p.name for p in clean.iterdir()}, {'locator.json', 'receipt.bin'})

    def test_committed_locator_restores_evidence_from_clean_git_clone(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'fixture-owner')
        backend = self.root / 'private-backend'
        saved = self.store.persist_observation_evidence(retained['id'], 'evidence-team', backend)
        self.store.export_publication(plan['id'], write=True)
        exported = self.store.paths.publications / plan['id'] / 'evidence' / (saved['id'] + '.json')
        repository = self.root / 'portable-publication'
        repository.mkdir()
        (repository / 'locator.json').write_bytes(exported.read_bytes())
        def git(*args):
            return subprocess.check_output(['git', '-C', str(repository), *args])
        git('init', '--quiet')
        git('add', 'locator.json')
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            'commit', '--quiet', '-m', 'test: retain portable evidence locator')
        commit = git('rev-parse', 'HEAD').decode().strip()
        trusted = hashlib.sha256(git('show', commit + ':locator.json')).hexdigest()
        clean = self.root / 'independent-git-consumer'
        subprocess.run(['git', 'clone', '--quiet', '--no-local', str(repository), str(clean)], check=True)
        subprocess.run(['git', '-C', str(clean), 'checkout', '--quiet', '--detach', commit], check=True)
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'archive', 'retrieve-evidence',
            '--repo', str(clean), '--path', 'locator.json', '--expected-sha256', trusted,
            '--backend-root', str(backend), '--destination', 'receipt.bin'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((clean / 'receipt.bin').read_bytes(), canonical(facts))
        self.assertEqual(subprocess.check_output(['git', '-C', str(clean), 'rev-parse', 'HEAD']).decode().strip(), commit)
        self.assertFalse((clean / 'creative.config.json').exists())
        self.assertFalse((clean / '.creative').exists())
        self.assertFalse(json.loads(result.stdout)['remote_verified'])

    def test_studio_http_retains_same_managed_evidence(self):
        import base64
        import json
        import export_engine
        from test_studio_release import StudioReleaseTests
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        self.store.config_path.write_text(json.dumps(self.config))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            retained, _ = StudioReleaseTests.request(self, ctx, '/api/publications/retain-evidence', {
                'observation_id': observation['id'], 'actor': 'fixture-owner', 'confirm': 'RETAIN',
                'evidence_base64': base64.b64encode(canonical(facts)).decode()})
        self.assertEqual(retained['observation_id'], observation['id'])
        self.assertEqual(self.store.verify_artifact(retained['artifact_id'])['sha256'], observation['evidence_sha256'])
        self.assertFalse((self.store.paths.publications / plan['id']).exists())

    def test_studio_invalid_evidence_requests_do_not_create_attempts(self):
        import base64
        import json
        import urllib.error
        import export_engine
        from test_studio_release import StudioReleaseTests
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        self.store.config_path.write_text(json.dumps(self.config))
        valid = {'observation_id': observation['id'], 'actor': 'fixture-owner', 'confirm': 'RETAIN',
                 'evidence_base64': base64.b64encode(canonical(facts)).decode()}
        records = self.store.paths.workspace / 'records'
        before = {str(p): p.read_bytes() for p in records.rglob('*.json')}
        changes = ({'confirm': 'UPLOAD'}, {'private_path': str(self.root)},
                   {'evidence_base64': 'invalid%%%'},
                   {'evidence_base64': base64.b64encode(b'wrong bytes').decode()})
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            for change in changes:
                with self.subTest(change=change):
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        StudioReleaseTests.request(self, ctx, '/api/publications/retain-evidence', {**valid, **change})
                    self.assertEqual(failure.exception.code, 400)
                    failure.exception.close()
                    self.assertEqual({str(p): p.read_bytes() for p in records.rglob('*.json')}, before)

    def test_studio_persistence_rejects_path_override_and_missing_backend(self):
        import json
        import urllib.error
        import export_engine
        from test_studio_release import StudioReleaseTests
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        self.store.config_path.write_text(json.dumps(self.config))
        valid = {'evidence_id': retained['id'], 'backend': 'missing', 'confirm': 'PERSIST'}
        records = self.store.paths.workspace / 'records'
        before = {str(p): p.read_bytes() for p in records.rglob('*.json')}
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            for changes in ({}, {'backend_root': str(self.root / 'unapproved')}, {'confirm': 'UPLOAD'}):
                with self.subTest(changes=changes):
                    with self.assertRaises(urllib.error.HTTPError) as failure:
                        StudioReleaseTests.request(self, ctx, '/api/publications/persist-evidence', {**valid, **changes})
                    self.assertEqual(failure.exception.code, 400)
                    failure.exception.close()
                    self.assertEqual({str(p): p.read_bytes() for p in records.rglob('*.json')}, before)
        self.assertFalse((self.root / 'unapproved').exists())

    def test_studio_persists_evidence_to_configured_private_backend(self):
        import json
        import export_engine
        from external_media_store import FileSystemMediaStore
        from test_studio_release import StudioReleaseTests
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        self.store.config_path.write_text(json.dumps(self.config))
        local = self.store.config_path.with_name(self.store.config_path.stem + '.local.json')
        (self.root / '.gitignore').write_text(local.name + '\n')
        backend = self.root / 'private-evidence-store'
        local.write_text(json.dumps({'schema_version': 1, 'project_id': self.config['project']['id'],
            'storage': {}, 'mediaBackends': {'evidence-team': {'provider': 'filesystem', 'root': str(backend)}}}))
        with export_engine.LocalServerContext(self.root, self.store.config_path) as ctx:
            saved, _ = StudioReleaseTests.request(self, ctx, '/api/publications/persist-evidence', {
                'evidence_id': retained['id'], 'backend': 'evidence-team', 'confirm': 'PERSIST'})
        self.assertIs(saved['retrieval_verified'], True)
        self.assertNotIn(str(self.root), json.dumps(saved))
        destination = self.root / 'independent-receipt.bin'
        FileSystemMediaStore('evidence-team', backend).retrieve(saved['reference'], destination)
        self.assertEqual(destination.read_bytes(), canonical(facts))

    def test_evidence_retention_cancellation_ends_attempt_without_binding(self):
        from unittest.mock import patch
        from pathlib import Path
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        for interrupt in (KeyboardInterrupt, SystemExit):
            with self.subTest(interrupt=interrupt.__name__):
                attempts = []
                original = self.store.start_attempt
                def start(*args, **kwargs):
                    value = original(*args, **kwargs)
                    attempts.append(value)
                    return value
                with patch.object(self.store, 'start_attempt', side_effect=start), patch.object(self.store, 'register', side_effect=interrupt):
                    with self.assertRaises(interrupt):
                        self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
                outcome = self.store._read('attempts', attempts[0]['id'], 'outcome')
                self.assertEqual(outcome['status'], 'cancelled')
                self.assertEqual((Path(attempts[0]['work_path']) / 'evidence.bin').read_bytes(), canonical(facts))
                self.assertFalse(list((self.store.paths.workspace / 'records/observation-evidence').glob('*.json')))

    def test_summary_registration_interruption_preserves_raw_and_retry_identity(self):
        from unittest.mock import patch
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        original_observation = self.store._path('remote-observations', observation['id']).read_bytes()
        for interruption, status in ((OSError('Injected summary failure'), 'failed'),
                                     (KeyboardInterrupt(), 'cancelled')):
            with self.subTest(status=status):
                registered = []
                original = self.store.register
                def register(attempt, source, role, **kwargs):
                    if role == 'observation-summary':
                        raise interruption
                    artifact = original(attempt, source, role, **kwargs)
                    registered.append(artifact)
                    return artifact
                with patch.object(self.store, 'register', side_effect=register):
                    with self.assertRaises(type(interruption)):
                        self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
                raw = registered[0]
                raw_record = self.store._path('artifacts', raw['id']).read_bytes()
                self.assertEqual(self.store.object_path(raw['sha256']).read_bytes(), canonical(facts))
                self.assertEqual(self.store._read('attempts', raw['attempt_id'], 'outcome')['status'], status)
                fresh = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
                self.assertNotEqual(raw['id'], fresh['artifact_id'])
                self.assertEqual(self.store._path('artifacts', raw['id']).read_bytes(), raw_record)
                self.assertEqual(self.store._path('remote-observations', observation['id']).read_bytes(), original_observation)
                self.assertNotIn(raw['id'], [self.store._read('observation-evidence', p.stem)['artifact_id']
                    for p in (self.store.paths.workspace / 'records/observation-evidence').glob('*.json')])

    def test_evidence_binding_failure_does_not_report_successful_attempt(self):
        from unittest.mock import patch
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        attempts = []
        original_start = self.store.start_attempt
        original_record = self.store._record
        def start(*args, **kwargs):
            result = original_start(*args, **kwargs)
            attempts.append(result)
            return result
        def record(category, *args, **kwargs):
            if category == 'observation-evidence':
                raise OSError('Injected binding failure')
            return original_record(category, *args, **kwargs)
        with patch.object(self.store, 'start_attempt', side_effect=start), patch.object(self.store, '_record', side_effect=record):
            with self.assertRaisesRegex(OSError, 'Injected binding failure'):
                self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        self.assertEqual(self.store._read('attempts', attempts[0]['id'], 'outcome')['status'], 'failed')

    def test_cancelled_evidence_binding_cannot_be_persisted(self):
        from unittest.mock import patch
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        original_finish = self.store.finish_attempt
        def finish(identity, status, **kwargs):
            if status == 'succeeded':
                raise KeyboardInterrupt
            return original_finish(identity, status, **kwargs)
        with patch.object(self.store, 'finish_attempt', side_effect=finish):
            with self.assertRaises(KeyboardInterrupt):
                self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        bindings = list((self.store.paths.workspace / 'records/observation-evidence').glob('*.json'))
        self.assertEqual(len(bindings), 1)
        binding = json.loads(bindings[0].read_text())
        with self.assertRaisesRegex(ValueError, 'producer is incomplete'):
            self.store.persist_observation_evidence(binding['id'], 'team', self.root / 'backend')
        self.assertFalse((self.root / 'backend').exists())
        with self.assertRaisesRegex(ValueError, 'producer is incomplete'):
            self.store.export_publication(plan['id'], write=True)
        self.assertFalse((self.store.paths.publications / plan['id']).exists())

    def test_sigkill_evidence_retention_recovers_without_overwriting_original(self):
        import json
        import os
        import signal
        import subprocess
        import sys
        import time
        from pathlib import Path
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        self.store.config_path.write_text(json.dumps(self.config))
        runtime = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'
        for point in ('artifact', 'binding'):
            with self.subTest(point=point):
                marker = self.root / ('crash-' + point + '.json')
                script = """
import json, os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from artifact_lifecycle import Lifecycle, canonical
root, config, observation, marker, point = sys.argv[2:]
core = Lifecycle(root, json.loads(Path(config).read_text()), Path(config))
original_start = core.start_attempt
original_record = core._record
original_register = core.register
def start(*args, **kwargs):
    kwargs['lease_seconds'] = 1
    result = original_start(*args, **kwargs)
    Path(marker).write_text(json.dumps(result))
    return result
def record(category, *args, **kwargs):
    result = original_record(category, *args, **kwargs)
    if point == 'binding' and category == 'observation-evidence':
        os.kill(os.getpid(), signal.SIGKILL)
    return result
def register(*args, **kwargs):
    result = original_register(*args, **kwargs)
    if point == 'artifact':
        os.kill(os.getpid(), signal.SIGKILL)
    return result
core.start_attempt = start
core._record = record
core.register = register
core.retain_observation_evidence(observation, canonical({'processing_state':'COMPLETE'}), 'crash-worker')
"""
                result = subprocess.run([sys.executable, '-c', script, str(runtime), str(self.root),
                    str(self.store.config_path), observation['id'], str(marker), point], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
                attempt = json.loads(marker.read_text())
                original = Path(attempt['work_path']) / 'evidence.bin'
                self.assertEqual(original.read_bytes(), canonical(facts))
                self.assertFalse(self.store._path('attempts', attempt['id'], 'outcome').exists())
                if point == 'binding':
                    records = list((self.store.paths.workspace / 'records/observation-evidence').glob('*.json'))
                    bound = next(json.loads(p.read_text()) for p in records
                        if self.store._read('artifacts', json.loads(p.read_text())['artifact_id'])['attempt_id'] == attempt['id'])
                    with self.assertRaisesRegex(ValueError, 'producer is incomplete'):
                        self.store.persist_observation_evidence(bound['id'], 'team', self.root / 'crash-backend')
                with self.assertRaisesRegex(ValueError, 'still active'):
                    self.store.recover_attempt(attempt['id'], 'recovery-owner', 'crash verified')
                time.sleep(1.1)
                recovered = self.store.recover_attempt(attempt['id'], 'recovery-owner', 'crash verified')
                self.assertEqual(recovered['retry_of'], attempt['id'])
                self.assertNotEqual(recovered['work_path'], attempt['work_path'])
                self.assertEqual(self.store._read('attempts', attempt['id'], 'outcome')['status'], 'interrupted')
                self.store.finish_attempt(recovered['id'], 'cancelled', reason='Explicitly close generic recovery before fresh retention')
                retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'recovery-owner')
                self.assertEqual(self.store.verify_artifact(retained['artifact_id'])['sha256'], observation['evidence_sha256'])
                self.assertEqual(original.read_bytes(), canonical(facts))

    def test_changed_evidence_binding_is_rejected_before_external_writes(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        binding = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        path = self.store._path('observation-evidence', binding['id'])
        original = path.read_bytes()
        changed = json.loads(original)
        changed['actor'] = 'forged-owner'
        path.write_bytes(canonical(changed))
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.persist_observation_evidence(binding['id'], 'team', self.root / 'forged-backend')
        with self.assertRaisesRegex(ValueError, 'commit event binding'):
            self.store.export_publication(plan['id'], write=True)
        self.assertFalse((self.root / 'forged-backend').exists())
        self.assertFalse((self.store.paths.publications / plan['id']).exists())
        self.assertEqual(path.read_bytes(), canonical(changed))

    def test_publication_status_reports_receipt_custody_without_private_paths(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        saved = self.store.persist_observation_evidence(retained['id'], 'team', self.root / 'private-backend')
        files = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        custody = self.store.publication_status(plan['id'])['evidence_custody']
        self.assertEqual(custody['records'][0]['evidence_id'], retained['id'])
        self.assertEqual(custody['records'][0]['observation_id'], observation['id'])
        self.assertTrue(custody['records'][0]['producer_succeeded'])
        self.assertEqual(custody['versions'][0]['id'], saved['id'])
        self.assertNotIn(str(self.root), json.dumps(custody))
        self.assertEqual({str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, files)
        self.assertFalse(self.store.publication_status(plan['id'])['remote_verified'])

    def test_custody_status_preserves_damaged_record_diagnostics_without_paths(self):
        import json
        plan = self.plan()
        facts = {'processing_state': 'COMPLETE'}
        observation = self.observe(plan, 'processing', facts)
        retained = self.store.retain_observation_evidence(observation['id'], canonical(facts), 'owner')
        saved = self.store.persist_observation_evidence(retained['id'], 'team', self.root / 'private-backend')
        binding_path = self.store._path('observation-evidence', retained['id'])
        external_path = self.store._path('external-media', saved['id'])
        changes = [(binding_path, {'actor': 'changed'}),
                   (external_path, {'reference': {**saved['reference'], 'root': str(self.root)}})]
        for path, fields in changes:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                damaged = canonical({**json.loads(original), **fields})
                path.write_bytes(damaged)
                before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
                try:
                    report = self.store.publication_status(plan['id'])
                    custody = report['evidence_custody']
                    self.assertTrue(custody['errors'])
                    self.assertEqual(custody['versions'], [])
                    self.assertFalse(custody['writes_performed'])
                    self.assertNotIn(str(self.root), json.dumps(custody))
                    self.assertFalse(report['remote_verified'])
                    self.assertEqual({str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
                finally:
                    path.write_bytes(original)
