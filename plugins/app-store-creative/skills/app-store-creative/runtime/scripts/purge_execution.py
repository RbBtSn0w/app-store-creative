"""Journaled permanent removal of exact redundant copies with original-plan recovery."""
import os
from pathlib import Path

from purge_guards import references, scan
from quarantine_commit import _matches, _move
from quarantine_inventory import _authority
from relocation_quarantine import _actor, _hash, _identity
from relocation_purge import _verify
from storage_control_projection import _sync_history


def _checkpoint(core, plan, index):
    item = plan['files'][index]
    return {'id': plan['quarantine_id'], 'plan_id': plan['id'], 'file': item,
            'tombstone': str(Path(item['path']).with_name(f".creative-purge-{plan['id']}-{index}"))}


def _existing_checkpoint(core, plan, index):
    path = core._path('maintenance', plan['quarantine_id'], f'purge-file-{index}')
    if not path.exists() and not path.is_symlink():
        return None
    record = core._read('maintenance', plan['quarantine_id'], f'purge-file-{index}')
    expected = _checkpoint(core, plan, index)
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError('Purge file checkpoint differs')
    return record


def _context(core, plan, historical=False):
    identity = plan['quarantine_id']; operation = core._read('maintenance', identity)
    _authority(core, operation, historical=historical)
    prepared = core._read('maintenance', identity, 'prepared')
    commit = core._read('maintenance', identity, 'commit-intent')
    outcome = core._read('maintenance', identity, 'quarantined')
    if (plan.get('operation') != 'relocation-purge-plan' or plan.get('storage') != (operation['storage'] if historical else core.paths.binding())
            or plan.get('operation_sha256') != _hash(operation) or plan.get('prepared_sha256') != _hash(prepared)
            or plan.get('commit_intent_sha256') != _hash(commit) or plan.get('quarantined_sha256') != _hash(outcome)):
        raise ValueError('Purge operation evidence differs')
    restore = core._path('maintenance', identity, 'restore-intent')
    if restore.exists() or restore.is_symlink():
        raise ValueError('Quarantine restoration has started')
    expected = []
    roots = {entry['source']['root']: entry['source']['directory_identity'] for entry in commit['files']}
    roots[operation['quarantine_root']] = operation['directory_identity']
    for index, entry in enumerate(commit['files']):
        item, payload = entry['source'], prepared['copies'][index]
        for path, file_id, parent_id, kind in (
                (entry['retained_path'], item['file_identity'], commit['parents'][str(Path(entry['retained_path']).parent)], 'source-side'),
                (payload['quarantine_path'], payload['file_identity'], operation['directory_identity'], 'prepared')):
            expected.append({'path': path, 'sha256': item['sha256'], 'size_bytes': item['size_bytes'],
                             'file_identity': file_id, 'parent_identity': parent_id, 'kind': kind})
    if plan.get('files') != expected or plan.get('guard_roots') != roots:
        raise ValueError('Purge file scope differs')
    return operation


def _preflight(core, plan):
    if references(core) != plan['references_sha256']:
        raise ValueError('Relocation purge plan is stale; references changed')
    for proof in plan['recovery']:
        for identity in proof['artifacts']:
            core.verify_artifact(identity)
        path = core.object_path(proof['sha256'])
        if str(path) != proof['path'] or not _matches(path, proof):
            raise ValueError('Purge recovery object changed')
    guard_view(core, plan)


def guard_view(core, plan):
    actual = {item['path']: item for item in scan(plan['guard_roots'])}
    expected = {item['path']: item for item in plan['guard_files']}
    for index, item in enumerate(plan['files']):
        checkpoint = _existing_checkpoint(core, plan, index)
        if checkpoint is None:
            continue
        target, tombstone = item['path'], checkpoint['tombstone']
        if target in actual and tombstone in actual:
            raise ValueError('Purge file location conflict')
        if tombstone in actual:
            observed = actual.pop(tombstone)
            actual[target] = {**observed, 'path': target}
        if target not in actual:
            expected.pop(target, None)
    if actual != expected:
        raise ValueError('Purge files changed; preserve unknown or conflicting data')

    return actual


def _delete(core, plan, index):
    item = plan['files'][index]; checkpoint = _existing_checkpoint(core, plan, index)
    if checkpoint is None:
        checkpoint = core._record('maintenance', _checkpoint(core, plan, index), f'purge-file-{index}')
    _sync_history(core._path('maintenance', plan['quarantine_id'], f'purge-file-{index}'), core.paths.workspace)
    source, tombstone = Path(item['path']), Path(checkpoint['tombstone'])
    if source.exists() or source.is_symlink():
        _move(source, tombstone, item, item['parent_identity'])
    if tombstone.exists() or tombstone.is_symlink():
        if not _matches(tombstone, item):
            raise ValueError('Purge captured file identity changed; preserve for investigation')
        fd = os.open(tombstone.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if [info.st_dev, info.st_ino] != item['parent_identity']:
                raise ValueError('Purge parent identity changed')
            info = os.stat(tombstone.name, dir_fd=fd, follow_symlinks=False)
            if [info.st_dev, info.st_ino] != item['file_identity']:
                raise ValueError('Purge captured file identity changed')
            os.unlink(tombstone.name, dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if [info.st_dev, info.st_ino] != item['parent_identity']:
                raise ValueError('Purge parent identity changed')
            os.fsync(fd)
        finally:
            os.close(fd)


def execute(core, plan_id, actor, reason):
    _actor(actor, reason)
    with core.transaction():
        plan = core._read('maintenance', plan_id)
        if plan.get('operation') != 'relocation-purge-plan':
            raise ValueError('Invalid relocation purge plan')
        identity = plan['quarantine_id']; path = core._path('maintenance', identity, 'purge-intent')
        if path.exists() or path.is_symlink():
            intent = core._read('maintenance', identity, 'purge-intent')
            if intent.get('plan_id') != plan_id or intent.get('plan_sha256') != _hash(plan):
                raise ValueError('Another or changed purge plan owns this operation')
        else:
            _verify(core, plan_id)
            intent = core._record('maintenance', {'id': identity, 'plan_id': plan_id,
                'plan_sha256': _hash(plan), 'actor': actor, 'reason': reason}, 'purge-intent')
        _sync_history(path, core.paths.workspace)
        _context(core, plan)
        completed = core._path('maintenance', identity, 'purged')
        if completed.exists():
            result = core._read('maintenance', identity, 'purged')
            if (result.get('status') != 'PURGED' or result.get('plan_id') != plan_id
                    or result.get('purge_intent_sha256') != _hash(intent)
                    or result.get('logical_bytes_removed') != sum(item['size_bytes'] for item in plan['files'])):
                raise ValueError('Purge completion evidence differs')
            if any(Path(item['path']).exists() or Path(item['path']).is_symlink()
                   or Path(_checkpoint(core, plan, index)['tombstone']).exists()
                   or Path(_checkpoint(core, plan, index)['tombstone']).is_symlink()
                   for index, item in enumerate(plan['files'])):
                raise ValueError('Purged files reappeared; preserve for investigation')
            if any(_existing_checkpoint(core, plan, index) is None for index in range(len(plan['files']))):
                raise ValueError('Completed purge file checkpoint missing')
            guard_view(core, plan)
            _sync_history(completed, core.paths.workspace)
            return result
        _preflight(core, plan)
        for index in range(len(plan['files'])):
            if _hash(core._read('maintenance', plan_id)) != _hash(plan) or _hash(core._read('maintenance', identity, 'purge-intent')) != _hash(intent):
                raise ValueError('Purge plan or intent changed during execution')
            _context(core, plan)
            _preflight(core, plan)
            _delete(core, plan, index)
        result = core._record('maintenance', {'id': identity, 'status': 'PURGED', 'plan_id': plan_id,
            'purge_intent_sha256': _hash(intent), 'logical_bytes_removed': sum(item['size_bytes'] for item in plan['files'])}, 'purged')
        _sync_history(completed, core.paths.workspace)
        return result
