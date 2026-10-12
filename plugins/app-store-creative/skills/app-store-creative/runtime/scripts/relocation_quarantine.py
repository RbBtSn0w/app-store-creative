"""Durable quarantine preparation; source removal is a separate operation."""
import hashlib
import os
from pathlib import Path
import shutil

from artifact_lifecycle import canonical, digest, identifier, safe_id
from relocation_retention import _verify
from storage_control_projection import _sync_history


def _hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _actor(actor, reason):
    if (not isinstance(actor, str) or not actor.strip()
            or not isinstance(reason, str) or not reason.strip()):
        raise ValueError('Quarantine preparation requires actor and reason')


def _root(core, identity):
    root = core.paths.workspace / 'maintenance/relocation-quarantine' / safe_id(identity)
    if root.resolve() != root:
        raise ValueError('Quarantine preparation path contains aliases')
    return root


def _identity(path):
    info = path.stat()
    return [info.st_dev, info.st_ino]


def _scope(core, operation):
    cancelled = core._path('maintenance', operation['id'], 'preparation-cancelled')
    if cancelled.exists() or cancelled.is_symlink():
        raise ValueError('Quarantine preparation was cancelled')
    if (operation.get('operation') != 'relocation-quarantine'
            or operation.get('storage') != core.paths.binding()
            or operation.get('config_path') != str(core.config_path)):
        raise ValueError('Invalid relocation quarantine operation')
    plan = _verify(core, operation['plan_id'])
    eligible = [item for item in plan['files'] if item['decision'] == 'eligible']
    root = _root(core, operation['id'])
    if (operation.get('plan_sha256') != _hash(plan) or operation.get('files') != eligible
            or operation.get('quarantine_root') != str(root) or not root.is_dir()
            or operation.get('directory_identity') != _identity(root)):
        raise ValueError('Quarantine preparation scope or directory identity changed')
    allowed = {f"{index}-{item['sha256']}" for index, item in enumerate(eligible)}
    if any(path.name not in allowed for path in root.iterdir()):
        raise ValueError('Quarantine preparation contains unknown files; preserve and inspect them')
    return root


def _copy(core, operation, index, item, root):
    destination = root / f"{index}-{item['sha256']}"
    suffix = f'copy-{index}'
    intent_path = core._path('maintenance', operation['id'], suffix)
    if destination.exists() or destination.is_symlink():
        intent = core._read('maintenance', operation['id'], suffix)
        if (destination.resolve() != destination or not destination.is_file()
                or intent.get('path') != str(destination) or intent.get('source') != item
                or intent.get('file_identity') != _identity(destination)):
            raise ValueError('Quarantine payload ownership changed')
    else:
        if intent_path.exists() or intent_path.is_symlink():
            raise ValueError('Quarantine payload missing after recorded creation')
        source = Path(item['path'])
        if source.resolve() != source:
            raise ValueError('Quarantine source path contains aliases')
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(source_fd)
            if [info.st_dev, info.st_ino] != item['file_identity'] or info.st_size != item['size_bytes']:
                raise ValueError('Quarantine source identity changed')
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                root_info = os.fstat(root_fd)
                if [root_info.st_dev, root_info.st_ino] != operation['directory_identity']:
                    raise ValueError('Quarantine directory identity changed')
                destination_fd = os.open(destination.name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root_fd)
            finally:
                os.close(root_fd)
            try:
                info = os.fstat(destination_fd)
                intent = core._record('maintenance', {'id': operation['id'], 'source': item,
                    'path': str(destination), 'file_identity': [info.st_dev, info.st_ino]}, suffix)
                _sync_history(intent_path, core.paths.workspace)
                with os.fdopen(os.dup(source_fd), 'rb') as input_stream, os.fdopen(os.dup(destination_fd), 'wb') as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
                    output_stream.flush(); os.fsync(output_stream.fileno())
            finally:
                os.close(destination_fd)
        finally:
            os.close(source_fd)
    if destination.resolve() != destination or _identity(destination) != intent['file_identity']:
        raise ValueError('Quarantine payload ownership changed')
    if destination.stat().st_size != item['size_bytes'] or digest(destination) != item['sha256']:
        raise ValueError('Partial or corrupt quarantine payload preserved; prepare a new operation')
    fd = os.open(destination, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync_history(destination, core.paths.workspace)
    if _identity(destination) != intent['file_identity']:
        raise ValueError('Quarantine payload ownership changed')
    return {'source': item, 'quarantine_path': str(destination), 'file_identity': _identity(destination)}


def _execute(core, operation):
    root = _scope(core, operation)
    copies = [_copy(core, operation, index, item, root) for index, item in enumerate(operation['files'])]
    # Copying may take time; references and both physical copies must still match.
    _scope(core, operation)
    record = {'id': operation['id'], 'status': 'PREPARED', 'operation_sha256': _hash(operation),
              'copies': copies, 'source_removal_executed': False}
    path = core._path('maintenance', operation['id'], 'prepared')
    if path.exists():
        completed = core._read('maintenance', operation['id'], 'prepared')
        if any(completed.get(key) != value for key, value in record.items()):
            raise ValueError('Quarantine preparation receipt differs')
        _sync_history(path, core.paths.workspace)
        return completed
    completed = core._record('maintenance', record, 'prepared')
    _sync_history(path, core.paths.workspace)
    return completed



def _attempt(core, operation):
    try:
        return _execute(core, operation)
    except (OSError, ValueError) as error:
        path = core._path('maintenance', operation['id'], 'preparation-failure')
        if not path.exists():
            core._record('maintenance', {'id': operation['id'], 'status': 'INTERRUPTED',
                'phase': 'quarantine-preparation', 'error_type': type(error).__name__,
                'source_removal_executed': False}, 'preparation-failure')
            _sync_history(path, core.paths.workspace)
        raise


def prepare(core, plan_id, actor, reason):
    _actor(actor, reason)
    with core.transaction():
        plan = _verify(core, plan_id)
        eligible = [item for item in plan['files'] if item['decision'] == 'eligible']
        if not eligible:
            raise ValueError('Relocation retention plan has no eligible files')
        identity = identifier()
        root = _root(core, identity)
        root.mkdir(parents=True, exist_ok=False)
        operation = core._record('maintenance', {'id': identity, 'operation': 'relocation-quarantine',
            'plan_id': plan_id, 'plan_sha256': _hash(plan), 'files': eligible,
            'storage': core.paths.binding(), 'config_path': str(core.config_path),
            'quarantine_root': str(root), 'directory_identity': _identity(root),
            'actor': actor, 'reason': reason})
        _sync_history(core._path('maintenance', identity), core.paths.workspace)
        _sync_history(root / 'payload', core.paths.workspace)
        return _attempt(core, operation)


def resume(core, operation_id, actor, reason):
    _actor(actor, reason)
    with core.transaction():
        operation = core._read('maintenance', operation_id)
        result = _attempt(core, operation)
        if not core._path('maintenance', operation_id, 'preparation-resumed').exists():
            core._record('maintenance', {'id': operation_id, 'actor': actor, 'reason': reason}, 'preparation-resumed')
            _sync_history(core._path('maintenance', operation_id, 'preparation-resumed'), core.paths.workspace)
        return result


def cancel(core, operation_id, actor, reason):
    _actor(actor, reason)
    with core.transaction():
        from quarantine_inventory import _authority
        operation = core._read('maintenance', operation_id)
        if operation.get('operation') != 'relocation-quarantine':
            raise ValueError('Invalid relocation quarantine operation')
        for suffix in ('commit-intent', 'purge-intent'):
            path = core._path('maintenance', operation_id, suffix)
            if path.exists() or path.is_symlink():
                raise ValueError('Quarantine commit has started; use its recovery workflow')
        _authority(core, operation)
        path = core._path('maintenance', operation_id, 'preparation-cancelled')
        if path.exists():
            result = core._read('maintenance', operation_id, 'preparation-cancelled')
        else:
            result = core._record('maintenance', {'id': operation_id, 'status': 'CANCELLED',
                'operation_sha256': _hash(operation), 'actor': actor, 'reason': reason,
                'source_removal_executed': False}, 'preparation-cancelled')
        _sync_history(path, core.paths.workspace)
        return result
