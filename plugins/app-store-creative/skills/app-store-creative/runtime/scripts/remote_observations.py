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


class ObservationOperations:
    def record_observation(self, publication_id, observation):
        from artifact_lifecycle import canonical, identifier
        allowed = {'plan_sha256', 'target', 'artifact_id', 'remote_id', 'gate', 'source',
                   'observed_at', 'evidence_reference', 'facts', 'supersedes'}
        if not isinstance(observation, dict) or set(observation) - allowed or not allowed - {'supersedes'} <= set(observation):
            raise ValueError('Invalid observation fields')
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

    def _publication_state(self, publication_id, max_age_seconds=86400):
        from artifact_lifecycle import canonical
        if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            raise ValueError('Observation freshness must be positive seconds')
        plan = self._read('publications', publication_id, 'plan')
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
        approvals = [self._read('approvals', p.stem) for p in (self.paths.workspace / 'records/approvals').glob('*.json')]
        approved = any(a.get('stage') == 'upload' and a.get('publication_id') == publication_id
                       and a.get('plan_sha256') == plan_hash and a.get('target') == plan['target'] for a in approvals)
        from pathlib import Path
        from delivery_lifecycle import verify_archive
        from publication_lifecycle import committed_archive
        import json
        archive_verified = False
        try:
            delivery = self._read('deliveries', plan['delivery_id'])
            package = self.delivery_path(delivery)
            verify_archive(package, plan['manifest_sha256'])
            committed_archive(self.paths.project, package, plan['archive_commit'],
                              json.loads((package / 'manifest.json').read_text()), plan['archive_path'])
            archive_verified = True
        except (ValueError, OSError):
            pass
        statuses = {item['status'] for item in gates}
        status = ('CONFLICT' if 'CONFLICT' in statuses else 'FAIL' if 'FAIL' in statuses
                  else 'FAIL' if not archive_verified
                  else 'PASS' if statuses == {'PASS'} and approved else 'UNKNOWN')
        return {'publication_id': publication_id, 'delivery_id': plan['delivery_id'], 'status': status,
                'remote_verified': status == 'PASS', 'remote_write': False, 'gates': gates,
                'remote_media_verified': statuses == {'PASS'}, 'archive_verified': archive_verified,
                'upload_approval': 'approved' if approved else 'pending', 'max_age_seconds': max_age_seconds,
                'reason': 'Derived from bound executor observations; missing or stale evidence remains UNKNOWN'}

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
        for path in (self.paths.workspace / 'records/approvals').glob('*.json'):
            approval = self._read('approvals', path.stem)
            if approval.get('stage') == 'upload' and approval.get('publication_id') == publication_id and approval.get('plan_sha256') == plan_hash:
                sanitized = {key: approval[key] for key in ('schema_version', 'created_at', 'id', 'stage', 'actor',
                    'publication_id', 'plan_sha256', 'target')}
                sanitized['authorization_reference_sha256'] = hashlib.sha256(approval['authorization_reference'].encode()).hexdigest()
                export('approvals', approval['id'], sanitized)
        return count
