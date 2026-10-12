"""Plan and verify permanent removal of exact redundant relocation quarantine copies."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path

from artifact_lifecycle import canonical, dependency_closure, digest, identifier
from quarantine_commit import _load, _check_locations, _matches
from relocation_quarantine import _hash, _identity
from relocation_retention import _configured_file


def _state(core, identity, quarantine_days):
    if type(quarantine_days) is not int or quarantine_days < 0:
        raise ValueError('Quarantine days must be a nonnegative integer')
    operation, prepared = _load(core, identity)
    if core._path('maintenance', identity, 'restore-intent').exists():
        raise ValueError('Quarantine restoration has started')
    purge_intent = core._path('maintenance', identity, 'purge-intent')
    if purge_intent.exists() or purge_intent.is_symlink():
        raise ValueError('Quarantine purge has started')
    outcome = core._read('maintenance', identity, 'quarantined')
    if outcome.get('status') != 'QUARANTINED':
        raise ValueError('Quarantine did not complete')
    if datetime.fromisoformat(outcome['created_at']) > datetime.now(timezone.utc) - timedelta(days=quarantine_days):
        raise ValueError('Quarantine retention has not expired')
    intent = core._read('maintenance', identity, 'commit-intent')
    _check_locations(intent)
    if any(Path(entry['source']['path']).exists() for entry in intent['files']):
        raise ValueError('Quarantine original source was restored')
    config = core._live_configuration()
    from relocation_inventory import inventory
    snapshot = inventory(core)
    if snapshot['staging'] or snapshot['unverified_operations'] or snapshot.get('disposition_errors'):
        raise ValueError('Purge blocked by pending or unverified relocation evidence')
    records = core.paths.workspace / 'records'
    artifacts = {path.stem: core._read('artifacts', path.stem) for path in (records / 'artifacts').glob('*.json')}
    protected = dependency_closure(sorted(core._incident_artifacts()), lambda key: artifacts[key])
    incident_hashes = {artifacts[key]['sha256'] for key in protected}
    files, recovery = [], {}
    for index, entry in enumerate(intent['files']):
        item = entry['source']; retained = Path(entry['retained_path'])
        payload = prepared['copies'][index]
        if item['sha256'] in incident_hashes:
            raise ValueError('Open incident protects relocation copies')
        if any(_configured_file(config, path, core.paths.project) for path in
               (Path(item['path']), retained, Path(payload['quarantine_path']))):
            raise ValueError('Purge file is a configured source path')
        row = next((row for row in snapshot['copies'] if row['relocation_id'] == item['relocation_id']
                    and row['group'] == item['group'] and row['path'] == item['root']), None)
        if row is None or row['status'] != 'QUARANTINED':
            raise ValueError('Retained source root is not verified quarantine')
        identities = sorted(key for key, value in artifacts.items() if value['sha256'] == item['sha256'])
        if not identities:
            raise ValueError('Missing registered recovery object')
        for key in identities:
            core.verify_artifact(key)
        active = core.object_path(item['sha256'])
        info = active.stat()
        if info.st_size != item['size_bytes'] or digest(active) != item['sha256']:
            raise ValueError('Current recovery object integrity failure')
        active_identity = [info.st_dev, info.st_ino]
        if active_identity in (item['file_identity'], payload['file_identity']):
            raise ValueError('Current recovery object is not independent')
        recovery[item['sha256']] = {'sha256': item['sha256'], 'size_bytes': item['size_bytes'],
            'path': str(active), 'file_identity': active_identity, 'artifacts': identities}
        for path, file_identity, parent_identity, kind in (
                (retained, item['file_identity'], intent['parents'][str(retained.parent)], 'source-side'),
                (Path(payload['quarantine_path']), payload['file_identity'], operation['directory_identity'], 'prepared')):
            if not _matches(path, {**item, 'file_identity': file_identity}):
                raise ValueError('Purge copy identity or bytes changed')
            files.append({'path': str(path), 'sha256': item['sha256'], 'size_bytes': item['size_bytes'],
                'file_identity': file_identity, 'parent_identity': parent_identity, 'kind': kind})
    references = []
    for path in sorted(records.rglob('*.json')):
        if 'maintenance' in path.relative_to(records).parts:
            continue
        if path.resolve() != path:
            raise ValueError('Purge reference records contain aliases')
        references.append([path.relative_to(records).as_posix(), digest(path)])
    state = {'files': files, 'recovery': [recovery[key] for key in sorted(recovery)],
             'operation_sha256': _hash(operation), 'prepared_sha256': _hash(prepared),
             'commit_intent_sha256': _hash(intent), 'quarantined_sha256': _hash(outcome)}
    from purge_guards import references as reference_guard, scan
    roots = {item['source']['root']: item['source']['directory_identity'] for item in intent['files']}
    roots[operation['quarantine_root']] = operation['directory_identity']
    state.update(references_sha256=reference_guard(core), guard_roots=roots, guard_files=scan(roots))
    state['snapshot_sha256'] = hashlib.sha256(canonical({'state': state, 'config': config,
        'references': references, 'inventory': snapshot})).hexdigest()
    return state


def plan(core, identity, quarantine_days):
    with core.transaction():
        state = _state(core, identity, quarantine_days)
        return core._record('maintenance', {'id': identifier(), 'operation': 'relocation-purge-plan',
            'quarantine_id': identity, 'quarantine_days': quarantine_days, 'storage': core.paths.binding(),
            **state, 'purge_executed': False})


def _verify(core, plan_id):
    record = core._read('maintenance', plan_id)
    if (record.get('operation') != 'relocation-purge-plan' or record.get('storage') != core.paths.binding()
            or record.get('purge_executed') is not False):
        raise ValueError('Invalid relocation purge plan')
    state = _state(core, record['quarantine_id'], record['quarantine_days'])
    if any(canonical(record.get(key)) != canonical(value) for key, value in state.items()):
        raise ValueError('Relocation purge plan is stale; create a new plan')
    return record


def verify(core, plan_id):
    with core.transaction():
        record = _verify(core, plan_id)
        return {'id': plan_id, 'status': 'READY', 'file_count': len(record['files']),
                'logical_bytes': sum(item['size_bytes'] for item in record['files']), 'purge_executed': False}
