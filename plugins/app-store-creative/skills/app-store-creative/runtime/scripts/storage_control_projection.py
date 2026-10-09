"""Journaled location projections; callers hold the storage mutation lock."""
import hashlib
import os
from pathlib import Path
import secrets

from artifact_lifecycle import canonical, safe_id


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_history(path, workspace):
    directory = path.parent
    while directory.is_relative_to(workspace):
        _sync(directory)
        if directory == workspace:
            _sync(directory.parent)
            return
        directory = directory.parent
    raise ValueError('Storage control history escapes workspace')


def _read(path):
    if path.resolve() != path or path.is_symlink():
        raise ValueError('Storage control path contains aliases')
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('Storage control must be a regular file')
    return path.read_bytes()


def _validate(category, key, record):
    if (not isinstance(record, dict) or type(record.get('schema_version')) is not int
            or record['schema_version'] != 1 or record.get('id') != key):
        raise ValueError('Storage control identity or schema differs')
    binding = record.get('to' if category == 'storage-activations' else 'from')
    if not isinstance(binding, dict) or hashlib.sha256(canonical(binding)).hexdigest() != key:
        raise ValueError('Storage control binding differs')
    safe_id(record.get('relocation_id', ''))
    sha = record.get('switch_sha256')
    if not isinstance(sha, str) or len(sha) != 64 or any(char not in '0123456789abcdef' for char in sha):
        raise ValueError('Storage control switch hash is invalid')


def publish(core, workspace, plan_id, category, key, before, after):
    """Update a journal-bound view without changing immutable business records.

    The relocation executor must first verify plan, receipt and project scope.
    This primitive preserves exact predecessor bytes and detects conflicting
    edits; it does not supply cross-process serialization or receipt approval.
    """
    if category not in ('storage-activations', 'storage-bindings'):
        raise ValueError('Storage control category cannot replace business records')
    plan_id, key = safe_id(plan_id), safe_id(key)
    workspace = Path(workspace)
    if not workspace.is_absolute() or workspace.resolve() != workspace:
        raise ValueError('Storage control workspace contains aliases')
    _validate(category, key, after)
    if before is not None:
        _validate(category, key, before)
    path = workspace / 'records' / category / (key + '.json')
    history = workspace / 'records/relocations' / plan_id / 'control-history' / category / (key + '.json')
    old_bytes = None if before is None else canonical(before)
    new_bytes = canonical(after)
    journal = {'schema_version': 1, 'id': plan_id, 'category': category, 'key': key,
               'before': before, 'after': after,
               'config_path': str(core.config_path),
               'project_id': core.config.get('project', {}).get('id')}
    journal_bytes = canonical(journal)
    saved = _read(history)
    if saved is not None and saved != journal_bytes:
        raise ValueError('Storage control journal differs from requested transition')
    actual = _read(path)
    if actual != old_bytes and not (saved is not None and actual == new_bytes):
        raise ValueError('Storage control precondition differs')
    if saved is None:
        core._write_path(history, journal)
    _sync_history(history, workspace)
    # The journal must be durable before a replacement can become visible.
    actual = _read(path)
    if actual != old_bytes and actual != new_bytes:
        raise ValueError('Storage control precondition changed after journal')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve() != path.parent:
        raise ValueError('Storage control parent contains aliases')
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.control-' + secrets.token_hex(16)
    created = False
    try:
        parent_stat = os.fstat(parent_fd)
        current_stat = path.parent.stat()
        if (parent_stat.st_dev, parent_stat.st_ino) != (current_stat.st_dev, current_stat.st_ino):
            raise ValueError('Storage control parent identity changed')
        if actual != new_bytes:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
            created = True
            with os.fdopen(fd, 'wb') as stream:
                stream.write(new_bytes); stream.flush(); os.fsync(stream.fileno())
            if _read(path) != actual:
                raise ValueError('Storage control precondition changed before replacement')
            current_stat = path.parent.stat()
            if (parent_stat.st_dev, parent_stat.st_ino) != (current_stat.st_dev, current_stat.st_ino):
                raise ValueError('Storage control parent identity changed before replacement')
            if actual is None:
                os.link(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            else:
                os.replace(temporary, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                created = False
        _sync(path.parent)
        os.fsync(parent_fd)
    finally:
        if created:
            os.unlink(temporary, dir_fd=parent_fd)
        os.close(parent_fd)
    _sync_history(path, workspace)
    return {'path': str(path), 'journal_path': str(history), 'status': 'PUBLISHED'}


def restore(core, workspace, plan_id, category, key, before, after):
    """Restore an unactivated operation's view while retaining its journal."""
    workspace = Path(workspace)
    plan_id, key = safe_id(plan_id), safe_id(key)
    if category not in ('storage-activations', 'storage-bindings'):
        raise ValueError('Storage control category cannot restore business records')
    _validate(category, key, after)
    if before is not None:
        _validate(category, key, before)
    path = workspace / 'records' / category / (key + '.json')
    previous = None if before is None else canonical(before)
    current = _read(path)
    if current == previous:
        if path.parent.exists():
            _sync_history(path, workspace)
        return
    journal = {'schema_version': 1, 'id': plan_id, 'category': category, 'key': key,
               'before': before, 'after': after, 'config_path': str(core.config_path),
               'project_id': core.config.get('project', {}).get('id')}
    history = workspace / 'records/relocations' / plan_id / 'control-history' / category / (key + '.json')
    if current != canonical(after) or _read(history) != canonical(journal):
        raise ValueError('Storage control rollback evidence differs')
    if before is not None:
        publish(core, workspace, plan_id + '-rollback', category, key, after, before)
    else:
        # This path was absent in the bound plan; remove only our exact view.
        if _read(path) != canonical(after):
            raise ValueError('Storage control rollback precondition changed')
        path.unlink()
        _sync_history(path, workspace)
