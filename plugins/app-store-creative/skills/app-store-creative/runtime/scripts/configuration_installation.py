"""Journal a replacement inode before rename so post-rename recovery has proof."""
import base64
import hashlib
import os
from pathlib import Path
import stat
from artifact_lifecycle import canonical
from configuration_layers import _identity, _read_regular, verify_local_git_protection, owning_document
from configuration_preparation import _sync_directory


IDENTITY_FIELDS = ('device', 'inode', 'mode', 'size_bytes', 'mtime_ns')


def installation_paths(core, plan_id, restoring=False):
    plan = core._read('relocations', plan_id)
    target = owning_document(core.paths.project, core.config_path, plan['configuration_change'])['path']
    action = 'rollback-install' if restoring else 'install'
    suffix = 'configuration-rollback-installation' if restoring else 'configuration-installation'
    temporary = target.with_name('.' + target.name + '.creative-' + action + '-' + plan_id + '.tmp')
    record = core._path('relocations', plan_id, suffix)
    return target, temporary, record


def _expected(core, plan_id, restoring=False):
    plan = core._read('relocations', plan_id)
    intent = core._read('relocations', plan_id, 'switch-intent')
    prepared = core._read('relocations', plan_id, 'configuration-prepared')
    change = plan['configuration_change']
    authority = owning_document(core.paths.project, core.config_path, change)
    payload = authority['target_bytes']
    mode = authority['mode']
    if (canonical(authority['effective_config']) != canonical(intent['target_config'])
            or prepared != intent.get('configuration_prepared') or intent['source_config_mode'] != mode):
        raise ValueError('Configuration installation authority differs')
    rollback_intent = None
    if restoring:
        rollback_intent = core._read('relocations', plan_id, 'rollback-intent')
        payload = base64.b64decode(intent['source_config_base64'], validate=True)
        if (payload != authority['source_bytes']
                or hashlib.sha256(payload).hexdigest() != plan['source_config_file_sha256']
                or rollback_intent.get('source_config_sha256') != plan['source_config_file_sha256']):
            raise ValueError('Configuration restoration authority differs')
    target, temporary, _ = installation_paths(core, plan_id, restoring)
    expected = {'id':plan_id, 'target_path':str(target), 'temporary_path':str(temporary),
                'target_sha256':hashlib.sha256(payload).hexdigest(),
                'plan_sha256':hashlib.sha256(canonical(plan)).hexdigest(),
                'prepared_sha256':hashlib.sha256(canonical(prepared)).hexdigest(), 'mode':mode}
    if restoring:
        expected['rollback_intent_sha256'] = hashlib.sha256(canonical(rollback_intent)).hexdigest()
    return expected, payload



def _verify_local_project_authority(core, plan_id):
    change = core._read('relocations', plan_id)['configuration_change']
    before = _identity(core.config_path)
    original = base64.b64decode(change['source_project_bytes_base64'], validate=True)
    if (before != change['source_project_identity'] or _read_regular(core.config_path) != original
            or _identity(core.config_path) != before):
        raise ValueError('Shared project configuration changed during local installation')


def verify_configuration_installation(core, plan_id, installed=False, restoring=False):
    expected, payload = _expected(core, plan_id, restoring)
    target, temporary, record = installation_paths(core, plan_id, restoring)
    if target != core.config_path:
        _verify_local_project_authority(core, plan_id)
        verify_local_git_protection(target)
    for path in (temporary, record):
        verify_local_git_protection(path)
    record_identity = _identity(record)
    proof = core._read('relocations', plan_id, record.stem)
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ValueError('Configuration installation evidence differs')
    path = target if installed else temporary
    observed = _identity(path)
    if (observed is None or not stat.S_ISREG(observed['mode']) or
            {key:observed[key] for key in IDENTITY_FIELDS} != proof.get('installed_identity')):
        raise ValueError('Configuration installation file identity changed')
    if _read_regular(path) != payload or _identity(path) != observed or _identity(record) != record_identity:
        raise ValueError('Configuration installation bytes or identity changed')
    return proof


def prepare_configuration_installation(core, plan_id, restoring=False):
    """Call under the source lock after prepared/source revalidation."""
    expected, payload = _expected(core, plan_id, restoring)
    target, temporary, record = installation_paths(core, plan_id, restoring)
    if target != core.config_path:
        _verify_local_project_authority(core, plan_id)
        verify_local_git_protection(target)
    for path in (temporary, record):
        verify_local_git_protection(path)
    if record.exists() or record.is_symlink():
        verify_configuration_installation(core, plan_id, restoring=restoring)
        _sync_directory(target.parent)
        _sync_directory(record.parent)
        verify_configuration_installation(core, plan_id, restoring=restoring)
        return temporary
    if target.parent.resolve() != target.parent:
        raise ValueError('Configuration installation parent changed')
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        os.fchmod(stream.fileno(), expected['mode'])
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        opened = os.fstat(stream.fileno())
    observed = _identity(temporary)
    if observed is None or (observed['device'], observed['inode']) != (opened.st_dev, opened.st_ino):
        raise ValueError('Configuration installation temporary identity changed')
    _sync_directory(target.parent)
    core._record('relocations', {**expected,
        'installed_identity':{key:observed[key] for key in IDENTITY_FIELDS}}, record.stem)
    _sync_directory(record.parent)
    verify_configuration_installation(core, plan_id, restoring=restoring)
    return temporary


def transfer_installation_proof(core, plan_id, workspace):
    """Copy late evidence excluded from the earlier media/operation publication."""
    _, _, record = installation_paths(core, plan_id)
    destination = Path(workspace) / 'records/relocations' / plan_id / record.name
    proof = core._read('relocations', plan_id, 'configuration-installation')
    if destination.exists() or destination.is_symlink():
        if destination.resolve() != destination or destination.read_bytes() != canonical(proof):
            raise ValueError('Configuration installation target evidence differs')
    else:
        core._write_path(destination, proof)
        _sync_directory(destination.parent)
