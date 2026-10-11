"""Bound executor observations and conservative remote completion gates."""
from datetime import datetime, timedelta, timezone
import hashlib
import re


FACTS = {
    'upload': {'found', 'source_checksum'},
    'processing': {'processing_state'},
    'media': {'media_verified'},
    'playback': {'media_verified'},
    'poster': {'poster_verified', 'poster_frame_time_code', 'poster_width', 'poster_height'},
}
SOURCES = {'asc-api', 'asc-cli', 'browser', 'media-probe', 'human-review'}


def validate_observation_facts(gate, facts):
    if not isinstance(facts, dict) or set(facts) - FACTS[gate]:
        raise ValueError('Unknown or sensitive observation facts')
    for key, value in facts.items():
        if key in ('found', 'media_verified', 'poster_verified') and not isinstance(value, bool):
            raise ValueError('Observation facts require boolean verification values')
        if key in ('poster_width', 'poster_height') and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError('Invalid poster dimensions')
        if key == 'source_checksum' and (not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value)):
            raise ValueError('Invalid source checksum')
        if key == 'processing_state' and value not in ('COMPLETE', 'FAILED', 'PROCESSING', 'UPLOADING', 'UNKNOWN'):
            raise ValueError('Unknown processing state')
        if key == 'poster_frame_time_code' and (not isinstance(value, str) or not re.fullmatch(r'[0-9:.]{1,32}', value)):
            raise ValueError('Invalid poster time code')


def observation_summary(observation):
    return {'schema_version': 1, **{key: observation[key] for key in (
        'id', 'publication_id', 'plan_sha256', 'artifact_id', 'gate', 'source',
        'observed_at', 'evidence_sha256', 'facts')}, 'observation_id': observation['id']}


def requirements(asset):
    return ['upload', 'processing', 'playback', 'poster'] if asset['role'] == 'preview' else ['upload', 'processing', 'media']


def gate_result(asset, gate, facts, source):
    if gate in ('upload', 'processing') and source not in {'asc-api', 'asc-cli'}:
        return 'UNKNOWN'
    if gate == 'upload':
        if facts.get('found') is False:
            return 'FAIL'
        if facts.get('found') is True and facts.get('source_checksum'):
            return 'PASS' if facts['source_checksum'] == asset['source_checksum'] else 'FAIL'
    elif gate == 'processing':
        return {'COMPLETE': 'PASS', 'FAILED': 'FAIL'}.get(facts.get('processing_state'), 'UNKNOWN')
    elif gate in ('media', 'playback'):
        if source not in {'browser', 'media-probe', 'human-review'}:
            return 'UNKNOWN'
        return {True: 'PASS', False: 'FAIL'}.get(facts.get('media_verified'), 'UNKNOWN')
    elif gate == 'poster':
        if facts.get('poster_verified') is False:
            return 'FAIL'
        expected = asset.get('poster_frame_time_code')
        actual = facts.get('poster_frame_time_code')
        if expected and actual and actual != expected:
            return 'FAIL'
        if (source in {'browser', 'media-probe', 'human-review'} and facts.get('poster_verified') is True
                and facts.get('poster_width', 0) > 0 and facts.get('poster_height', 0) > 0
                and expected and actual == expected):
            return 'PASS'
    return 'UNKNOWN'


def retrieve_observation_evidence(path, expected_sha256, backend_root, destination):
    from configuration_layers import _read_regular
    from external_media_store import FileSystemMediaStore
    import json
    payload = _read_regular(path)
    if (not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256)
            or hashlib.sha256(payload).hexdigest() != expected_sha256):
        raise ValueError('Observation evidence locator differs from trusted hash')
    locator = json.loads(payload)
    fields = {'schema_version', 'id', 'observation_id', 'publication_id', 'plan_sha256', 'evidence_sha256', 'reference', 'summary', 'summary_sha256'}
    if (not isinstance(locator, dict) or set(locator) != fields
            or type(locator.get('schema_version')) is not int or locator['schema_version'] != 1
            or any(not isinstance(locator[key], str) or not re.fullmatch('[0-9a-f]{32}', locator[key])
                   for key in ('id', 'observation_id', 'publication_id'))
            or any(not isinstance(locator[key], str) or not re.fullmatch('[0-9a-f]{64}', locator[key])
                   for key in ('plan_sha256', 'evidence_sha256'))
            or not isinstance(locator['reference'], dict)
            or locator['reference'].get('sha256') != locator['evidence_sha256']):
        raise ValueError('Invalid portable observation evidence locator')
    from artifact_lifecycle import canonical
    summary = locator['summary']
    summary_fields = {'schema_version', 'id', 'publication_id', 'plan_sha256', 'artifact_id',
        'gate', 'source', 'observed_at', 'evidence_sha256', 'facts', 'observation_id'}
    if (not isinstance(summary, dict) or set(summary) != summary_fields
            or type(summary.get('schema_version')) is not int or summary['schema_version'] != 1
            or summary['id'] != locator['observation_id'] or summary['observation_id'] != locator['observation_id']
            or summary['publication_id'] != locator['publication_id']
            or summary['plan_sha256'] != locator['plan_sha256']
            or summary['evidence_sha256'] != locator['evidence_sha256']
            or not isinstance(summary['gate'], str) or summary['gate'] not in FACTS
            or not isinstance(summary['source'], str) or summary['source'] not in SOURCES
            or not isinstance(summary['facts'], dict) or set(summary['facts']) - FACTS[summary['gate']]
            or not isinstance(locator['summary_sha256'], str)
            or hashlib.sha256(canonical(summary)).hexdigest() != locator['summary_sha256']):
        raise ValueError('Invalid portable observation evidence summary')
    if (not isinstance(summary['artifact_id'], str)
            or not re.fullmatch('[0-9a-f]{32}', summary['artifact_id'])
            or not isinstance(summary['observed_at'], str)):
        raise ValueError('Invalid portable observation evidence summary values')
    try:
        observed = datetime.fromisoformat(summary['observed_at'])
    except ValueError as error:
        raise ValueError('Invalid portable observation evidence summary time') from error
    if observed.tzinfo is None:
        raise ValueError('Invalid portable observation evidence summary time')
    validate_observation_facts(summary['gate'], summary['facts'])
    store = FileSystemMediaStore(locator['reference'].get('backend'), backend_root)
    result = store.retrieve(locator['reference'], destination)
    return {**result, 'observation_id': locator['observation_id'],
            'publication_id': locator['publication_id'], 'locator_sha256': expected_sha256,
            'remote_verified': False, 'summary': summary, 'summary_sha256': locator['summary_sha256']}


class ObservationOperations:
    def record_observation(self, publication_id, observation, evidence):
        from artifact_lifecycle import canonical, identifier
        allowed = {'plan_sha256', 'target', 'artifact_id', 'remote_id', 'gate', 'source',
                   'observed_at', 'evidence_reference', 'evidence_sha256', 'facts', 'supersedes'}
        if not isinstance(observation, dict) or set(observation) - allowed or not allowed - {'supersedes'} <= set(observation):
            raise ValueError('Invalid observation fields')
        if (not isinstance(evidence, bytes) or not evidence
                or not isinstance(observation['evidence_sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', observation['evidence_sha256'])
                or hashlib.sha256(evidence).hexdigest() != observation['evidence_sha256']):
            raise ValueError('Observation evidence bytes differ from evidence SHA-256')
        with self.transaction():
            plan = self._read('publications', publication_id, 'plan')
            plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
            if observation['plan_sha256'] != plan_hash or observation['target'] != plan['target']:
                raise ValueError('Observation scope differs from publication plan')
            asset = next((a for a in plan['assets'] if a['artifact_id'] == observation['artifact_id']), None)
            gate = observation['gate']; source = observation['source']; facts = observation['facts']
            if not asset or gate not in requirements(asset) or source not in SOURCES:
                raise ValueError('Observation artifact, gate or source is outside scope')
            for key in ('remote_id', 'evidence_reference'):
                value = observation[key]
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,256}', value) or value.startswith(('/', 'file:', 'http:', 'https:')):
                    raise ValueError('Observation references must be sanitized executor identities')
            validate_observation_facts(gate, facts)
            observed = datetime.fromisoformat(observation['observed_at'])
            if observed.tzinfo is None or observed > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError('Observation time must be timezone-aware and not in the future')
            supersedes = observation.get('supersedes', [])
            if not isinstance(supersedes, list) or len(set(supersedes)) != len(supersedes):
                raise ValueError('Supersession requires unique observation identities')
            for identity in supersedes:
                prior = self._read('remote-observations', identity)
                if any(prior[key] != observation[key] for key in ('artifact_id', 'gate', 'plan_sha256')) or prior['publication_id'] != publication_id:
                    raise ValueError('Supersession crosses observation scope')
                if datetime.fromisoformat(prior['observed_at']) > observed:
                    raise ValueError('Supersession cannot use an older observation')
            return self._record('remote-observations', {'id': identifier(), 'publication_id': publication_id,
                **observation, 'supersedes': supersedes,
                'verdict': gate_result(asset, gate, facts, source)})

    def retain_observation_evidence(self, observation_id, evidence, actor):
        from artifact_lifecycle import canonical, identifier
        from pathlib import Path
        with self.transaction():
            observation = self._read('remote-observations', observation_id)
            if (not isinstance(evidence, bytes) or not evidence
                    or hashlib.sha256(evidence).hexdigest() != observation['evidence_sha256']):
                raise ValueError('Observation evidence bytes differ from recorded hash')
            plan = self._read('publications', observation['publication_id'], 'plan')
            if (hashlib.sha256(canonical(plan)).hexdigest() != observation['plan_sha256']
                    or plan['target'] != observation['target']):
                raise ValueError('Observation scope differs from publication plan')
            self._verify_publication_archive(plan)
            delivery = self._read('deliveries', plan['delivery_id'])
            candidate = self._read('candidates', delivery['candidate_id'])
        attempt = self.start_attempt(candidate['run_id'], 'observation-evidence', actor)
        try:
            source = Path(attempt['work_path']) / 'evidence.bin'
            source.write_bytes(evidence)
            artifact = self.register(attempt['id'], source, 'observation-evidence',
                                     media_type='application/octet-stream', inputs=[observation['artifact_id']])
            summary_path = Path(attempt['work_path']) / 'summary.json'
            summary_path.write_bytes(canonical(observation_summary(observation)))
            summary = self.register(attempt['id'], summary_path, 'observation-summary',
                                    media_type='application/json', inputs=[artifact['id']])
            with self.transaction():
                current = self._read('remote-observations', observation_id)
                if current != observation:
                    raise ValueError('Observation changed during evidence retention')
                binding = self._record('observation-evidence', {'id': identifier(), 'observation_id': observation_id,
                    'publication_id': observation['publication_id'], 'artifact_id': artifact['id'],
                    'evidence_sha256': observation['evidence_sha256'], 'actor': actor,
                    'summary_artifact_id': summary['id'], 'summary_sha256': summary['sha256']})
            self.finish_attempt(attempt['id'], 'succeeded')
            return binding
        except (KeyboardInterrupt, SystemExit):
            self.finish_attempt(attempt['id'], 'cancelled', reason='Observation evidence retention cancelled')
            raise
        except Exception:
            self.finish_attempt(attempt['id'], 'failed', reason='Observation evidence retention failed')
            raise

    def _verify_observation_summary(self, binding, observation):
        from artifact_lifecycle import canonical
        if (not isinstance(binding.get('summary_artifact_id'), str)
                or not re.fullmatch('[0-9a-f]{32}', binding['summary_artifact_id'])
                or not isinstance(binding.get('summary_sha256'), str)
                or not re.fullmatch('[0-9a-f]{64}', binding['summary_sha256'])):
            raise ValueError('Missing or invalid observation summary binding')
        summary = self.verify_artifact(binding['summary_artifact_id'])
        expected = canonical(observation_summary(observation))
        if (summary['role'] != 'observation-summary'
                or summary['inputs'] != [binding['artifact_id']]
                or summary['sha256'] != binding['summary_sha256']
                or self.object_path(summary['sha256']).read_bytes() != expected):
            raise ValueError('Observation summary differs from evidence binding')
        errors = self.source_eligibility_errors(summary['id'])
        if errors:
            raise ValueError('Observation evidence producer is incomplete: ' + '; '.join(errors))
        return summary

    def persist_observation_evidence(self, evidence_id, backend, backend_root=None):
        from external_media_store import persist_managed
        with self.transaction():
            binding = self._read('observation-evidence', evidence_id)
            observation = self._read('remote-observations', binding['observation_id'])
            artifact = self.verify_artifact(binding['artifact_id'])
            self._verify_observation_summary(binding, observation)
            errors = self.source_eligibility_errors(artifact['id'])
            if errors:
                raise ValueError('Observation evidence producer is incomplete: ' + '; '.join(errors))
            if (binding['publication_id'] != observation['publication_id']
                    or artifact['role'] != 'observation-evidence'
                    or artifact['sha256'] != observation['evidence_sha256']
                    or binding['evidence_sha256'] != observation['evidence_sha256']):
                raise ValueError('Observation evidence binding differs from managed artifact')
        return persist_managed(self, artifact['id'], backend, backend_root)

    def _publication_state(self, publication_id, max_age_seconds=86400):
        from artifact_lifecycle import safe_id
        safe_id(publication_id)
        from artifact_lifecycle import canonical
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            raise ValueError('Observation freshness must be positive seconds')
        try:
            plan = self._read('publications', publication_id, 'plan')
        except (ValueError, OSError):
            # An unreadable plan cannot supply trusted delivery or media identities.
            return {'publication_id': publication_id, 'delivery_id': None, 'status': 'FAIL',
                    'remote_verified': False, 'remote_write': False, 'gates': [],
                    'evidence_custody': {'records': [], 'versions': [],
                        'errors': ['Publication plan could not be verified.'], 'writes_performed': False},
                    'remote_media_verified': False, 'archive_verified': False,
                    'retrieval_verified': False, 'upload_approval': 'pending',
                    'max_age_seconds': max_age_seconds, 'approval_errors': [],
                    'reason': 'Publication plan could not be verified. Inspect saved records before retrying.'}
        plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
        observations = [self._read('remote-observations', path.stem)
                        for path in (self.paths.workspace / 'records/remote-observations').glob('*.json')]
        observations = [o for o in observations if o['publication_id'] == publication_id]
        superseded = {identity for item in observations for identity in item['supersedes']}
        active = [o for o in observations if o['id'] not in superseded]
        gates = []
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        for asset in plan['assets']:
            scoped = [o for o in active if o['artifact_id'] == asset['artifact_id']]
            remote_ids = {o['remote_id'] for o in scoped}
            for gate in requirements(asset):
                matching = [o for o in scoped if o['gate'] == gate]
                verdicts = {gate_result(asset, gate, o['facts'], o['source']) if datetime.fromisoformat(o['observed_at']) >= cutoff else 'UNKNOWN'
                            for o in matching}
                if len(remote_ids) > 1 or {'PASS', 'FAIL'} <= verdicts:
                    verdict = 'CONFLICT'
                elif 'FAIL' in verdicts:
                    verdict = 'FAIL'
                elif verdicts == {'PASS'}:
                    verdict = 'PASS'
                else:
                    verdict = 'UNKNOWN'
                gates.append({'artifact_id': asset['artifact_id'], 'gate': gate, 'status': verdict,
                              'observations': [o['id'] for o in matching]})
        approvals = self._approval_status_records()
        approved = any(not errors and self._upload_approval_matches(a, plan, plan_hash) for a, errors in approvals)
        from pathlib import Path
        from delivery_lifecycle import verify_archive
        from publication_lifecycle import committed_archive
        import json
        try:
            self._require_retrieval_proof(plan)
            retrieval_verified = True
        except ValueError:
            retrieval_verified = False
        archive_verified = False
        try:
            self._verify_publication_archive(plan)
            archive_verified = True
        except (ValueError, OSError):
            pass
        statuses = {item['status'] for item in gates}
        status = ('CONFLICT' if 'CONFLICT' in statuses else 'FAIL' if 'FAIL' in statuses
                  else 'FAIL' if not archive_verified or not retrieval_verified
                  else 'PASS' if statuses == {'PASS'} and approved else 'UNKNOWN')
        return {'publication_id': publication_id, 'delivery_id': plan['delivery_id'], 'status': status,
                'remote_verified': status == 'PASS', 'remote_write': False, 'gates': gates,
                'evidence_custody': self._evidence_custody(publication_id, hashlib.sha256(canonical(plan)).hexdigest()),
                'remote_media_verified': statuses == {'PASS'}, 'archive_verified': archive_verified,
                'retrieval_verified': retrieval_verified,
                'upload_approval': 'approved' if approved else 'pending', 'max_age_seconds': max_age_seconds,
                'approval_errors': [{'id': a['id'], 'errors': errors} for a, errors in approvals if errors],
                'reason': 'Derived from bound executor observations; missing or stale evidence remains UNKNOWN'}

    def _evidence_custody(self, publication_id, plan_hash):
        records = []
        try:
            for path in sorted((self.paths.workspace / 'records/observation-evidence').glob('*.json')):
                binding = self._read('observation-evidence', path.stem)
                if binding['publication_id'] != publication_id:
                    continue
                observation = self._read('remote-observations', binding['observation_id'])
                artifact = self.verify_artifact(binding['artifact_id'])
                self._verify_observation_summary(binding, observation)
                if (observation['publication_id'] != publication_id or observation['plan_sha256'] != plan_hash
                        or artifact['role'] != 'observation-evidence'
                        or artifact['sha256'] != observation['evidence_sha256']
                        or binding['evidence_sha256'] != observation['evidence_sha256']):
                    raise ValueError('Invalid evidence custody scope')
                records.append({'evidence_id': binding['id'], 'observation_id': observation['id'],
                    'artifact_id': artifact['id'], 'sha256': artifact['sha256'],
                    'producer_succeeded': not self.source_eligibility_errors(artifact['id'])})
            versions = self._observation_evidence_exports(publication_id, plan_hash)
            return {'records': records, 'versions': versions, 'errors': [], 'writes_performed': False}
        except (ValueError, OSError, KeyError, TypeError):
            return {'records': records, 'versions': [],
                    'errors': ['Evidence custody could not be verified. Inspect saved records before retrying.'],
                    'writes_performed': False}

    def _observation_evidence_exports(self, publication_id, plan_hash):
        exports = []
        records = self.paths.workspace / 'records'
        for path in (records / 'observation-evidence').glob('*.json'):
            binding = self._read('observation-evidence', path.stem)
            observation = self._read('remote-observations', binding['observation_id'])
            if observation['publication_id'] != publication_id or observation['plan_sha256'] != plan_hash:
                continue
            artifact = self.verify_artifact(binding['artifact_id'])
            self._verify_observation_summary(binding, observation)
            errors = self.source_eligibility_errors(artifact['id'])
            if errors:
                raise ValueError('Observation evidence producer is incomplete: ' + '; '.join(errors))
            if (binding['publication_id'] != publication_id or artifact['role'] != 'observation-evidence'
                    or binding['evidence_sha256'] != observation['evidence_sha256']
                    or artifact['sha256'] != observation['evidence_sha256']):
                raise ValueError('Observation evidence binding differs from managed artifact')
            for external_path in (records / 'external-media').glob('*.json'):
                saved = self._read('external-media', external_path.stem)
                if saved['artifact_id'] != artifact['id']:
                    continue
                reference = saved.get('reference')
                fields = {'schema_version', 'provider', 'backend', 'object_id', 'version', 'sha256', 'size_bytes'}
                if (saved.get('retrieval_verified') is not True or not isinstance(reference, dict)
                        or set(reference) != fields or type(reference.get('schema_version')) is not int
                        or reference['schema_version'] != 1 or reference['provider'] != 'filesystem'
                        or not isinstance(reference['backend'], str)
                        or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', reference['backend'])
                        or reference['sha256'] != artifact['sha256']
                        or reference['version'] != artifact['sha256']
                        or reference['object_id'] != 'sha256:' + artifact['sha256']
                        or type(reference['size_bytes']) is not int or reference['size_bytes'] != artifact['size_bytes']):
                    raise ValueError('Invalid portable observation evidence reference')
                exports.append({'schema_version': 1, 'id': saved['id'], 'observation_id': observation['id'],
                    'publication_id': publication_id, 'plan_sha256': plan_hash,
                    'evidence_sha256': observation['evidence_sha256'], 'reference': reference,
                    'summary': observation_summary(observation), 'summary_sha256': binding['summary_sha256']})
        return exports

    def _export_observation_records(self, publication_id, plan_hash):
        from artifact_lifecycle import canonical
        root = self.paths.publications / publication_id
        count = 0
        def export(category, identity, data):
            path = root / category / (identity + '.json')
            if path.resolve() != path:
                raise ValueError('Publication evidence path is symlinked')
            if path.exists():
                if path.read_bytes() != canonical(data):
                    raise ValueError('Existing immutable publication evidence differs')
            else:
                self._write_path(path, data)
        for path in (self.paths.workspace / 'records/remote-observations').glob('*.json'):
            observation = self._read('remote-observations', path.stem)
            if observation['publication_id'] == publication_id and observation['plan_sha256'] == plan_hash:
                export('observations', observation['id'], observation)
                count += 1
        for evidence in self._observation_evidence_exports(publication_id, plan_hash):
            export('evidence', evidence['id'], evidence)
        plan = self._read('publications', publication_id, 'plan')
        for path in (self.paths.workspace / 'records/approvals').glob('*.json'):
            approval = self._read('approvals', path.stem)
            if self._upload_approval_matches(approval, plan, plan_hash):
                sanitized = {key: approval[key] for key in ('schema_version', 'created_at', 'id', 'stage', 'actor',
                    'publication_id', 'plan_sha256', 'target')}
                sanitized['authorization_reference_sha256'] = hashlib.sha256(approval['authorization_reference'].encode()).hexdigest()
                export('approvals', approval['id'], sanitized)
        return count
