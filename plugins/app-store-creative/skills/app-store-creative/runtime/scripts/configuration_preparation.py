"""Prepare an owning-layer configuration update without activating new storage.

The private journal and adjacent payload are recoverable evidence for a later
switch executor. This module deliberately performs no configuration replacement.
"""
import base64
import hashlib
import os
from pathlib import Path
import stat

from artifact_lifecycle import canonical, safe_id
from configuration_layers import _identity, _read_regular, verify_local_git_protection, verify_storage_change


CATEGORY = 'configuration-changes'


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _entry_identity(entry):
    return {'device':entry.st_dev, 'inode':entry.st_ino, 'mode':entry.st_mode}


def prepare_storage_change(core, plan, operation_id, actor, reason):
    """Create or revalidate a private staged payload under workspace ownership."""
    safe_id(operation_id)
    if not all(isinstance(value, str) and value.strip() for value in (actor, reason)):
        raise ValueError('Configuration preparation requires an actor and reason')
    verified = verify_storage_change(core.paths.project, core.config_path, plan)
    if verified['source_binding'] != core.paths.binding():
        raise ValueError('Configuration preparation requires the effective storage binding')
    target = Path(verified['target_path'])
    staged = target.with_name('.' + target.name + '.creative-' + operation_id + '.tmp')
    intent_path = core._path(CATEGORY, operation_id, 'intent')
    protected_paths = (staged, *(core._path(CATEGORY, operation_id, name)
                                for name in ('intent', 'created', 'prepared')))
    for path in protected_paths:
        verify_local_git_protection(path)
    if target.parent.resolve() != target.parent:
        raise ValueError('Configuration staging parent is symlinked')
    parent = _entry_identity(target.parent.lstat())
    intent = {'id':operation_id, 'operation':'configuration-storage-change-preparation',
              'plan':verified, 'actor':actor, 'reason':reason, 'staged_path':str(staged),
              'parent_identity':parent}
    payload = base64.b64decode(verified['target_bytes_base64'], validate=True)
    with core.transaction():
        verify_storage_change(core.paths.project, core.config_path, plan)
        for path in protected_paths:
            verify_local_git_protection(path)
        if intent_path.exists() or intent_path.is_symlink():
            recorded = core._read(CATEGORY, operation_id, 'intent')
            if any(recorded.get(key) != value for key, value in intent.items()):
                raise ValueError('Configuration preparation intent differs or is stale')
        else:
            core._record(CATEGORY, intent, 'intent')
            _sync_directory(intent_path.parent)
        directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if _entry_identity(os.fstat(directory_fd)) != parent:
                raise ValueError('Configuration staging parent identity changed')
            created_path = core._path(CATEGORY, operation_id, 'created')
            if created_path.exists() or created_path.is_symlink():
                created = core._read(CATEGORY, operation_id, 'created')
                descriptor = os.open(staged.name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            else:
                # An unjournaled existing file is never claimed, overwritten or removed.
                descriptor = os.open(staged.name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                                     0o600, dir_fd=directory_fd)
                try:
                    created = core._record(CATEGORY, {'id':operation_id,
                        'staged_path':str(staged), 'identity':_entry_identity(os.fstat(descriptor))}, 'created')
                    _sync_directory(created_path.parent)
                except BaseException:
                    os.close(descriptor)
                    raise
            with os.fdopen(descriptor, 'r+b') as stream:
                entry = os.fstat(stream.fileno())
                if (not stat.S_ISREG(entry.st_mode) or _entry_identity(entry) != created.get('identity')
                        or created.get('staged_path') != str(staged)):
                    raise ValueError('Configuration staging identity or ownership changed')
                prepared_path = core._path(CATEGORY, operation_id, 'prepared')
                prepared = core._read(CATEGORY, operation_id, 'prepared') if prepared_path.exists() else None
                observed = stream.read(len(payload) + 1)
                if prepared is not None:
                    if _identity(staged) != prepared.get('staged_identity'):
                        raise ValueError('Prepared configuration staging identity changed')
                elif observed == b'':
                    stream.seek(0); stream.write(payload); stream.flush()
                if observed not in (b'', payload) or (prepared is not None and observed != payload):
                    raise ValueError('Configuration staging payload is incomplete or changed')
                os.fsync(stream.fileno())
                final_identity = _identity(staged)
                if final_identity is None or final_identity['inode'] != entry.st_ino or final_identity['device'] != entry.st_dev:
                    raise ValueError('Configuration staging identity changed during preparation')
            _sync_directory(target.parent)
            if _entry_identity(target.parent.lstat()) != parent:
                raise ValueError('Configuration staging parent identity changed')
            if _read_regular(staged) != payload or _identity(staged) != final_identity:
                raise ValueError('Configuration staging changed during verification')
            verify_storage_change(core.paths.project, core.config_path, plan)
            for path in protected_paths:
                verify_local_git_protection(path)
            receipt = {'id':operation_id, 'state':'PREPARED', 'target_path':str(target),
                       'staged_path':str(staged), 'staged_identity':final_identity,
                       'target_sha256':hashlib.sha256(payload).hexdigest(),
                       'source_revision':verified['source_revision'], 'target_revision':verified['target_revision'],
                       'plan_sha256':hashlib.sha256(canonical(verified)).hexdigest(), 'storage_activated':False}
            if prepared is not None:
                if any(prepared.get(key) != value for key, value in receipt.items()):
                    raise ValueError('Prepared configuration receipt differs')
                return verify_prepared_storage_change(core, plan, operation_id)
            result = core._record(CATEGORY, receipt, 'prepared')
            _sync_directory(prepared_path.parent)
            return verify_prepared_storage_change(core, plan, operation_id)
        finally:
            os.close(directory_fd)


def verify_prepared_storage_change(core, plan, operation_id):
    """Reobserve prepared evidence without creating records or mutating payloads."""
    safe_id(operation_id)
    verified = verify_storage_change(core.paths.project, core.config_path, plan)
    if verified['source_binding'] != core.paths.binding():
        raise ValueError('Prepared configuration source storage differs')
    target = Path(verified['target_path'])
    staged = target.with_name('.' + target.name + '.creative-' + operation_id + '.tmp')
    paths = {name:core._path(CATEGORY, operation_id, name) for name in ('intent', 'created', 'prepared')}
    for path in (staged, *paths.values()):
        verify_local_git_protection(path)
    if target.parent.resolve() != target.parent:
        raise ValueError('Prepared configuration parent identity changed')
    parent_identity = _entry_identity(target.parent.lstat())
    identities = {name:_identity(path) for name, path in paths.items()}
    records = {name:core._read(CATEGORY, operation_id, name) for name in paths}
    intent, created, receipt = (records[name] for name in ('intent', 'created', 'prepared'))
    expected_intent = {'operation':'configuration-storage-change-preparation', 'plan':verified,
                       'staged_path':str(staged), 'parent_identity':parent_identity}
    if (any(intent.get(key) != value for key, value in expected_intent.items()) or
            not all(isinstance(intent.get(key), str) and intent[key].strip() for key in ('actor', 'reason'))):
        raise ValueError('Prepared configuration intent differs or is invalid')
    identity = _identity(staged)
    if (identity is None or not stat.S_ISREG(identity['mode']) or
            created.get('staged_path') != str(staged) or
            created.get('identity') != {key:identity[key] for key in ('device', 'inode', 'mode')}):
        raise ValueError('Prepared configuration staging identity or ownership changed')
    payload = base64.b64decode(verified['target_bytes_base64'], validate=True)
    expected = {'state':'PREPARED', 'target_path':str(target), 'staged_path':str(staged),
                'staged_identity':identity, 'target_sha256':hashlib.sha256(payload).hexdigest(),
                'source_revision':verified['source_revision'], 'target_revision':verified['target_revision'],
                'plan_sha256':hashlib.sha256(canonical(verified)).hexdigest(), 'storage_activated':False}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError('Prepared configuration receipt differs or staging identity changed')
    if _read_regular(staged) != payload:
        raise ValueError('Prepared configuration payload changed')
    # Reobserve every authority, including absence, permissions and actual Git rules.
    verify_storage_change(core.paths.project, core.config_path, plan)
    if (_identity(staged) != identity or _entry_identity(target.parent.lstat()) != parent_identity or
            any(_identity(path) != identities[name] for name, path in paths.items())):
        raise ValueError('Prepared configuration evidence identity changed during verification')
    for path in (staged, *paths.values()):
        verify_local_git_protection(path)
    return receipt


class _RelocationConfigurationCore:
    """Bind preparation records to a relocation while its caller holds the lock.

    Relocation evidence is copied separately from the immutable media snapshot.
    This adapter cannot acquire a transaction; use only inside the source lock.
    """
    def __init__(self, core):
        self.core = core
        self.paths = core.paths
        self.config_path = core.config_path

    def transaction(self):
        from contextlib import nullcontext
        return nullcontext()

    def _path(self, category, identity, suffix=None):
        if category != CATEGORY or suffix not in ('intent', 'created', 'prepared'):
            raise ValueError('Unsupported relocation configuration record')
        return self.core._path('relocations', identity, 'configuration-' + suffix)

    def _read(self, category, identity, suffix=None):
        self._path(category, identity, suffix)
        return self.core._read('relocations', identity, 'configuration-' + suffix)

    def _record(self, category, data, suffix=None):
        self._path(category, data['id'], suffix)
        return self.core._record('relocations', data, 'configuration-' + suffix)
