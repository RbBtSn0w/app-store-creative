"""Journaled source displacement and identity-preserving quarantine restoration."""
import ctypes
import errno
import os
from pathlib import Path
import sys

from artifact_lifecycle import digest
from quarantine_inventory import _authority
from relocation_quarantine import _actor, _hash, _identity
from relocation_retention import _verify
from storage_control_projection import _sync_history


def _matches(path, item):
    return (path.resolve() == path and path.is_file() and _identity(path) == item['file_identity']
            and path.stat().st_size == item['size_bytes'] and digest(path) == item['sha256'])


def _entries(operation):
    return [{'source': item, 'retained_path': str(Path(item['path']).with_name(
        f".creative-quarantine-{operation['id']}-{index}"))} for index, item in enumerate(operation['files'])]


def _load(core, identity):
    operation = core._read('maintenance', identity)
    root, expected, intents, phase = _authority(core, operation)
    if phase == 'CANCELLED':
        raise ValueError('Quarantine preparation was cancelled')
    if phase in ('PREPARING', 'INTERRUPTED'):
        raise ValueError('Quarantine preparation has not completed')
    if root.resolve() != root or not root.is_dir() or _identity(root) != operation['directory_identity']:
        raise ValueError('Quarantine preparation directory identity changed')
    if {path.name for path in root.iterdir()} != set(expected):
        raise ValueError('Quarantine preparation contains unknown or missing files')
    for name, item in expected.items():
        payload = root / name
        if not _matches(payload, {**item, 'file_identity': intents[name]['file_identity']}):
            raise ValueError('Quarantine preparation media changed')
    prepared = core._read('maintenance', identity, 'prepared')
    return operation, prepared


def _intent(core, operation, prepared, actor, reason):
    identity = operation['id']; path = core._path('maintenance', identity, 'commit-intent')
    if path.exists() or path.is_symlink():
        intent = core._read('maintenance', identity, 'commit-intent')
        if (intent.get('operation_sha256') != _hash(operation) or intent.get('prepared_sha256') != _hash(prepared)
                or intent.get('files') != _entries(operation)):
            raise ValueError('Quarantine commit intent differs')
        return intent
    _verify(core, operation['plan_id'])
    entries = _entries(operation)
    parents = {}
    for entry in entries:
        source = Path(entry['source']['path']); target = Path(entry['retained_path'])
        if not _matches(source, entry['source']) or target.exists() or target.is_symlink():
            raise ValueError('Quarantine source or reserved location changed')
        root = Path(entry['source']['root'])
        if _identity(root) != entry['source']['directory_identity']:
            raise ValueError('Quarantine source root identity changed')
        parents[str(source.parent)] = _identity(source.parent)
    intent = core._record('maintenance', {'id': identity, 'operation_sha256': _hash(operation),
        'prepared_sha256': _hash(prepared), 'files': entries, 'parents': parents,
        'actor': actor, 'reason': reason}, 'commit-intent')
    _sync_history(path, core.paths.workspace)
    return intent


def _move(source, destination, item, parent_identity):
    if source.parent != destination.parent or source.parent.resolve() != source.parent:
        raise ValueError('Quarantine move parent contains aliases')
    fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if [info.st_dev, info.st_ino] != parent_identity or not _matches(source, item):
            raise ValueError('Quarantine move identity changed')
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == 'darwin':
            call = libc.renameatx_np
            call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            flag = 4
        elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
            call = libc.renameat2
            call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            flag = 1
        else:
            raise ValueError('Exclusive quarantine move unavailable')
        if call(fd, os.fsencode(source.name), fd, os.fsencode(destination.name), flag):
            code = ctypes.get_errno()
            if code in (errno.EEXIST, errno.ENOTEMPTY):
                raise ValueError('Quarantine destination already exists')
            raise OSError(code, os.strerror(code))
        info = os.stat(destination.name, dir_fd=fd, follow_symlinks=False)
        if [info.st_dev, info.st_ino] != item['file_identity']:
            raise ValueError('Quarantine moved file identity differs; preserve for recovery')
        os.fsync(fd)
    finally:
        os.close(fd)


def _check_locations(intent):
    for entry in intent['files']:
        root = Path(entry['source']['root'])
        if root.resolve() != root or _identity(root) != entry['source']['directory_identity']:
            raise ValueError('Quarantine source root identity changed')
        source, retained = Path(entry['source']['path']), Path(entry['retained_path'])
        if source.exists() or source.is_symlink():
            if not _matches(source, entry['source']) or retained.exists() or retained.is_symlink():
                raise ValueError('Quarantine source location conflict')
        elif not _matches(retained, entry['source']):
            raise ValueError('Quarantine retained location conflict')
        if _identity(source.parent) != intent['parents'][str(source.parent)]:
            raise ValueError('Quarantine source parent identity changed')


def commit(core, identity, actor, reason):
    _actor(actor, reason)
    with core.transaction():
        operation, prepared = _load(core, identity)
        if core._path('maintenance', identity, 'restore-intent').exists():
            raise ValueError('Quarantine restoration has started')
        intent = _intent(core, operation, prepared, actor, reason)
        _check_locations(intent)
        completed_path = core._path('maintenance', identity, 'quarantined')
        if completed_path.exists():
            if any(Path(entry['source']['path']).exists() for entry in intent['files']):
                raise ValueError('Completed quarantine source location changed')
            result = core._read('maintenance', identity, 'quarantined')
            _sync_history(completed_path, core.paths.workspace)
            return result
        _verify(core, operation['plan_id'], intent['files'])
        for entry in intent['files']:
            source, retained = Path(entry['source']['path']), Path(entry['retained_path'])
            if source.exists():
                _move(source, retained, entry['source'], intent['parents'][str(source.parent)])
        path = core._path('maintenance', identity, 'quarantined')
        if path.exists():
            result = core._read('maintenance', identity, 'quarantined')
            if result.get('commit_intent_sha256') != _hash(intent):
                raise ValueError('Quarantine completion differs')
        else:
            result = core._record('maintenance', {'id': identity, 'status': 'QUARANTINED',
                'commit_intent_sha256': _hash(intent), 'source_removal_executed': True}, 'quarantined')
        _sync_history(path, core.paths.workspace)
        return result


def restore(core, identity, actor, reason):
    _actor(actor, reason)
    with core.transaction():
        purge = core._path('maintenance', identity, 'purge-intent')
        if purge.exists() or purge.is_symlink():
            raise ValueError('Quarantine purge has started; recovery is unavailable')
        operation, prepared = _load(core, identity)
        intent = core._read('maintenance', identity, 'commit-intent')
        if (intent.get('operation_sha256') != _hash(operation) or intent.get('prepared_sha256') != _hash(prepared)
                or intent.get('files') != _entries(operation)):
            raise ValueError('Quarantine restore intent differs')
        _check_locations(intent)
        path = core._path('maintenance', identity, 'restore-intent')
        if path.exists():
            if core._read('maintenance', identity, 'restore-intent').get('commit_intent_sha256') != _hash(intent):
                raise ValueError('Quarantine restore ownership differs')
        else:
            core._record('maintenance', {'id': identity, 'commit_intent_sha256': _hash(intent),
                'actor': actor, 'reason': reason}, 'restore-intent')
        _sync_history(path, core.paths.workspace)
        for entry in intent['files']:
            source, retained = Path(entry['source']['path']), Path(entry['retained_path'])
            if not source.exists():
                _move(retained, source, entry['source'], intent['parents'][str(source.parent)])
        path = core._path('maintenance', identity, 'restored')
        if path.exists():
            result = core._read('maintenance', identity, 'restored')
            if result.get('commit_intent_sha256') != _hash(intent):
                raise ValueError('Quarantine restored receipt differs')
        else:
            result = core._record('maintenance', {'id': identity, 'status': 'RESTORED',
                'commit_intent_sha256': _hash(intent), 'actor': actor, 'reason': reason}, 'restored')
        _sync_history(path, core.paths.workspace)
        return result
