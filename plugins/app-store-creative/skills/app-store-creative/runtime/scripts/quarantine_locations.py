"""Receipt-bound locations of quarantine copies; business records stay immutable."""
from pathlib import Path

from artifact_lifecycle import digest
from inventory_lifecycle import files_without_links
from relocation_quarantine import _hash


def _identity(path):
    if path.resolve() != path or path.is_symlink():
        raise ValueError('Quarantine location contains aliases')
    if not path.exists():
        return None
    info = path.stat()
    return [info.st_dev, info.st_ino]


def staged_workspace(core, plan):
    _, groups, staging = core._relocation_layout(plan)
    workspace = Path(plan['to']['workspace'])
    for key, final in groups.items():
        if workspace.is_relative_to(final):
            return Path(staging[key]) / workspace.relative_to(final)
    return workspace


def _snapshot(root):
    identity = _identity(root)
    if identity is None:
        return {'directory_identity': None, 'files': []}
    if not root.is_dir():
        raise ValueError('Quarantine location must be a directory')
    files, links = files_without_links(root, strict=True)
    if links:
        raise ValueError('Quarantine location contains unsafe links')
    result = []
    for path in files:
        info = path.stat()
        result.append({'path': path.relative_to(root).as_posix(), 'sha256': digest(path),
                       'size_bytes': info.st_size, 'file_identity': [info.st_dev, info.st_ino]})
    if _identity(root) != identity:
        raise ValueError('Quarantine location changed while observing')
    return {'directory_identity': identity, 'files': sorted(result, key=lambda item: item['path'])}


def capture(core, plan):
    workspace = staged_workspace(core, plan)
    copies = []
    for path in sorted((core.paths.workspace / 'records/maintenance').glob('*.json')):
        operation = core._read('maintenance', path.stem)
        if operation.get('operation') != 'relocation-quarantine':
            continue
        relative = Path('maintenance/relocation-quarantine') / operation['id']
        source, target = core.paths.workspace / relative, workspace / relative
        # Empty registered directories have no file manifest entry to create them.
        if source.is_dir() and not target.exists() and workspace != core.paths.workspace:
            target.mkdir(parents=True, exist_ok=False)
        copies.append({'id': operation['id'], 'operation_sha256': _hash(operation),
                       'relative_path': relative.as_posix(), **_snapshot(target)})
    return copies


def verify_at(core, prepared, workspace):
    expected = {path.stem for path in (core.paths.workspace / 'records/maintenance').glob('*.json')
                if core._read('maintenance', path.stem).get('operation') == 'relocation-quarantine'}
    entries = prepared.get('quarantine_locations', [])
    if (not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries)
            or len(entries) != len(expected) or {entry.get('id') for entry in entries} != expected):
        raise ValueError('Prepared quarantine location proof differs')
    for entry in entries:
        relative = Path('maintenance/relocation-quarantine') / entry['id']
        if (entry.get('relative_path') != relative.as_posix()
                or entry.get('operation_sha256') != _hash(core._read('maintenance', entry['id']))
                or _snapshot(workspace / relative) != {key: entry[key] for key in ('directory_identity', 'files')}):
            raise ValueError('Prepared quarantine location proof differs')


def verify_prepared(core, plan, prepared):
    verify_at(core, prepared, staged_workspace(core, plan))


def has_projection(core, operation):
    key = _hash(core.paths.binding())
    path = core._path('storage-activations', key)
    if not path.exists() and not path.is_symlink():
        return False
    activation = core._read('storage-activations', key)
    prepared = core._read('relocations', activation['relocation_id'], 'prepared')
    return any(entry.get('id') == operation['id'] for entry in prepared.get('quarantine_locations', []))


def resolve(core, operation):
    """Resolve only a completed switch's copy; never infer ownership from a path."""
    binding = core.paths.binding()
    activation = core._read('storage-activations', _hash(binding))
    plan_id = activation['relocation_id']
    plan = core._read('relocations', plan_id)
    intent = core._read('relocations', plan_id, 'switch-intent')
    prepared = core._read('relocations', plan_id, 'prepared')
    receipt = core._read('relocations', plan_id, 'switched')
    if (plan.get('to') != binding or receipt != intent.get('receipt') or receipt.get('status') != 'SWITCHED'
            or receipt.get('to') != binding or receipt.get('from') != plan.get('from')
            or receipt.get('project_id') != core.config.get('project', {}).get('id')
            or receipt.get('config_path') != str(core.config_path)
            or activation.get('to') != binding or activation.get('switch_sha256') != _hash(receipt)
            or intent.get('plan_sha256') != _hash(plan) or intent.get('prepared_sha256') != _hash(prepared)):
        raise ValueError('Quarantine location switch evidence differs')
    core._verified_relocation_controls(plan, intent)
    core._verify_staging_root_proofs(prepared)
    _, groups, staging = core._relocation_layout(plan)
    workspace = core.paths.workspace
    group = next((key for key, final in groups.items() if workspace.is_relative_to(final)), None)
    if group is not None:
        proof = core._read('relocations', plan_id, 'staging-root-' + group)
        if _identity(groups[group]) != proof.get('directory_identity'):
            raise ValueError('Quarantine workspace location identity differs')
    elif _identity(workspace) != plan.get('source_root_identities', {}).get('workspace',
            plan.get('occupied_root_identities', {}).get('workspace')):
        raise ValueError('Quarantine retained workspace identity differs')
    relative = Path('maintenance/relocation-quarantine') / operation['id']
    entries = [entry for entry in prepared.get('quarantine_locations', []) if entry.get('id') == operation['id']]
    if (len(entries) != 1 or entries[0].get('operation_sha256') != _hash(operation)
            or entries[0].get('relative_path') != relative.as_posix()):
        raise ValueError('Quarantine location copy evidence missing or changed')
    return core.paths.workspace / relative, entries[0]


def _backup_snapshot(path, relative):
    parent = path / relative
    result = {relative.as_posix(): _snapshot(parent)}
    if parent.is_dir():
        for child in sorted(parent.iterdir()):
            if child.is_dir() or child.is_symlink():
                result[(relative / child.name).as_posix()] = _snapshot(child)
    return result


def capture_backups(plan, prepared):
    result = {}
    workspace = Path(plan['to']['workspace'])
    for root in prepared['exchange_roots']:
        final = Path(root['destination'])
        if root['operation'] == 'EXCHANGE' and workspace.is_relative_to(final):
            relative = workspace.relative_to(final) / 'maintenance/relocation-quarantine'
            result[root['group']] = _backup_snapshot(final, relative)
    return result


def verify_backup(plan, intent, group, path):
    workspace = Path(plan['to']['workspace'])
    root = next(root for root in intent['roots'] if root['group'] == group)
    final = Path(root['destination'])
    if not workspace.is_relative_to(final):
        return
    relative = workspace.relative_to(final) / 'maintenance/relocation-quarantine'
    expected = intent.get('backup_quarantine_locations', {}).get(group)
    if _backup_snapshot(path, relative) != expected:
        raise ValueError('Backup quarantine location proof differs')
