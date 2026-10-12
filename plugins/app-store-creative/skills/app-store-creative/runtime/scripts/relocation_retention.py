"""Plan retention of relocation copies without deleting media or recovery evidence."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path

from artifact_lifecycle import canonical, digest, identifier
from relocation_inventory import _verified_roots, inventory


def _configured_file(config, path, project):
    if isinstance(config, dict):
        return any(_configured_file(value, path, project) for value in config.values())
    if isinstance(config, list):
        return any(_configured_file(value, path, project) for value in config)
    if not isinstance(config, str) or not config:
        return False
    candidate = Path(config)
    if not candidate.is_absolute():
        candidate = project / candidate
    return candidate.resolve() == path


def _state(core, cutoff, displaced=None):
    config = core._live_configuration()
    snapshot = inventory(core, displaced)
    files, excluded = [], []
    records = core.paths.workspace / 'records'
    registered = {core._read('artifacts', path.stem)['sha256']
                  for path in (records / 'artifacts').glob('*.json')}
    for copy in snapshot['copies']:
        if copy['status'] != 'VERIFIED':
            excluded.append(copy)
            continue
        move = core._read('relocations', copy['relocation_id'])
        switched = core._read('relocations', move['id'], 'switched')
        if move['operation'] == 'relocation-plan':
            from forward_source_copies import verify
            roots = verify(core, move)
            object_root = Path(move['from']['objects'])
        else:
            roots = _verified_roots(core, move)
            object_root = Path(move['to']['objects'])
        root, manifest = next((root, manifest) for root, manifest in roots
                              if root['staging'] == copy['path'] and root['group'] == copy['group'])
        original_root = Path(root.get('destination', root['staging']))
        for name, expected in sorted(manifest.items()):
            source = Path(copy['path']) / name
            original = original_root / name
            sha = expected['sha256']
            item = {'relocation_id': move['id'], 'group': copy['group'],
                    'path': str(source), 'relative_path': name, 'sha256': sha,
                    'size_bytes': expected['size_bytes'], 'root': copy['path'],
                    'directory_identity': copy['expected_directory_identity'],
                    'decision': 'protected', 'reason': 'retained-evidence'}
            physical = next((Path(entry['retained_path']) for entry in displaced or []
                             if entry['source']['path'] == str(source) and not source.exists()), source)
            info = physical.stat()
            item['file_identity'] = [info.st_dev, info.st_ino]
            files.append(item)
            if sha not in registered or original != object_root / sha[:2] / sha:
                continue
            if snapshot['staging'] or snapshot['unverified_operations'] or snapshot.get('disposition_errors'):
                item['reason'] = 'pending-operation-or-unverified-evidence'
                continue
            if datetime.fromisoformat(switched['created_at']) > cutoff:
                item['reason'] = 'retention-not-expired'
                continue
            if _configured_file(config, source, core.paths.project):
                item['reason'] = 'configured-source-path'
                continue
            item['reason'] = 'no-verified-independent-copy'
            try:
                recovery = core.object_path(sha)
                if (not recovery.is_file() or recovery.stat().st_size != expected['size_bytes']
                        or digest(recovery) != sha):
                    continue
                actual, retained = recovery.stat(), physical.stat()
                if (actual.st_dev, actual.st_ino) == (retained.st_dev, retained.st_ino):
                    continue
                item.update(decision='eligible', reason='verified-independent-object',
                            recovery={'path': str(recovery), 'sha256': sha,
                                      'size_bytes': actual.st_size,
                                      'file_identity': [actual.st_dev, actual.st_ino]})
            except (OSError, ValueError):
                continue
    references = []
    for path in sorted(records.rglob('*.json')):
        if 'maintenance' in path.relative_to(records).parts:
            continue
        if path.resolve() != path or path.is_symlink():
            raise ValueError('Symlinked lifecycle record')
        references.append([path.relative_to(records).as_posix(), digest(path)])
    fingerprint = hashlib.sha256(canonical({'config': config, 'inventory': snapshot,
        'files': files, 'references': references})).hexdigest()
    return {'snapshot_sha256': fingerprint, 'files': files, 'excluded_roots': excluded,
            'staging': snapshot['staging'], 'unverified_operations': snapshot['unverified_operations']}


def plan(core, retention_days):
    if type(retention_days) is not int or retention_days < 0:
        raise ValueError('Retention days must be a nonnegative integer')
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    with core.transaction():
        state = _state(core, cutoff)
        return core._record('maintenance', {'id': identifier(), 'operation': 'relocation-retention-plan',
            'retention_days': retention_days, 'cutoff': cutoff.isoformat(),
            'storage': core.paths.binding(), **state, 'cleanup_executed': False})


def _verify(core, plan_id, displaced=None):
    record = core._read('maintenance', plan_id)
    if (record.get('operation') != 'relocation-retention-plan'
            or record.get('storage') != core.paths.binding()
            or type(record.get('retention_days')) is not int or record['retention_days'] < 0
            or record.get('cleanup_executed') is not False):
        raise ValueError('Invalid relocation retention plan')
    cutoff = datetime.fromisoformat(record['cutoff'])
    created = datetime.fromisoformat(record['created_at'])
    if (cutoff.tzinfo is None or created.tzinfo is None or cutoff > created
            or created - cutoff < timedelta(days=record['retention_days'])):
        raise ValueError('Invalid relocation retention cutoff')
    state = _state(core, cutoff, displaced)
    if any(canonical(record.get(key)) != canonical(value) for key, value in state.items()):
        raise ValueError('Relocation retention plan is stale; create a new plan')
    return record


def verify(core, plan_id):
    with core.transaction():
        record = _verify(core, plan_id)
        eligible = [item for item in record['files'] if item['decision'] == 'eligible']
        return {'id': plan_id, 'status': 'READY', 'eligible_file_count': len(eligible),
                'eligible_bytes': sum(item['size_bytes'] for item in eligible), 'cleanup_executed': False}
