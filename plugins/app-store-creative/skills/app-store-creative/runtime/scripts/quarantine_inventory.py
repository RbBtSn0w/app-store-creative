"""Read-only, evidence-bound observations of relocation quarantine preparations."""
import hashlib
from pathlib import Path

from artifact_lifecycle import canonical, digest, safe_id
from inventory_lifecycle import files_without_links


def _hash(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _identity(value):
    return isinstance(value, list) and len(value) == 2 and all(type(item) is int and item >= 0 for item in value)


def _authority(core, operation, historical=False):
    identity = operation['id']
    binding = core.paths.binding()
    if historical:
        binding = operation.get('storage')
        if core.resolve_storage_binding(binding) != core.paths.binding():
            raise ValueError('Historical maintenance binding differs')
    root = Path(binding['workspace']) / 'maintenance/relocation-quarantine' / safe_id(identity)
    plan = core._read('maintenance', operation['plan_id'])
    if (operation.get('storage') != binding or operation.get('config_path') != str(core.config_path)
            or operation.get('quarantine_root') != str(root) or not _identity(operation.get('directory_identity'))
            or plan.get('operation') != 'relocation-retention-plan' or plan.get('storage') != binding
            or operation.get('plan_sha256') != _hash(plan)
            or operation.get('files') != [item for item in plan['files'] if item['decision'] == 'eligible']):
        raise ValueError('Quarantine operation authority differs')
    prepared_path = core._path('maintenance', identity, 'prepared')
    prepared = core._read('maintenance', identity, 'prepared') if prepared_path.exists() or prepared_path.is_symlink() else None
    expected, intents = {}, {}
    for index, item in enumerate(operation['files']):
        name = f"{index}-{item['sha256']}"
        expected[name] = item
        path = core._path('maintenance', identity, f'copy-{index}')
        if path.exists() or path.is_symlink():
            intent = core._read('maintenance', identity, f'copy-{index}')
            if (intent.get('path') != str(root / name) or intent.get('source') != item
                    or not _identity(intent.get('file_identity'))):
                raise ValueError('Quarantine copy creation evidence differs')
            intents[name] = intent
    if prepared is not None:
        copies = [{'source': item, 'quarantine_path': str(root / name),
                   'file_identity': intents[name]['file_identity']} for name, item in expected.items() if name in intents]
        if (len(copies) != len(expected) or prepared.get('operation_sha256') != _hash(operation)
                or prepared.get('status') != 'PREPARED' or prepared.get('source_removal_executed') is not False
                or prepared.get('copies') != copies):
            raise ValueError('Quarantine preparation receipt differs')
    interrupted = core._path('maintenance', identity, 'preparation-failure')
    failure = None
    if interrupted.exists() or interrupted.is_symlink():
        failure = core._read('maintenance', identity, 'preparation-failure')
        if (failure.get('status') != 'INTERRUPTED' or failure.get('phase') != 'quarantine-preparation'
                or failure.get('source_removal_executed') is not False):
            raise ValueError('Quarantine interruption evidence differs')
    phase = 'PREPARED' if prepared else ('INTERRUPTED' if failure else 'PREPARING')
    commit_path = core._path('maintenance', identity, 'commit-intent')
    commit = core._read('maintenance', identity, 'commit-intent') if commit_path.exists() or commit_path.is_symlink() else None
    if commit:
        entries = [{'source': item, 'retained_path': str(Path(item['path']).with_name(
            f".creative-quarantine-{identity}-{index}"))} for index, item in enumerate(operation['files'])]
        parents = {str(Path(item['path']).parent) for item in operation['files']}
        if (prepared is None or commit.get('operation_sha256') != _hash(operation)
                or commit.get('prepared_sha256') != _hash(prepared) or commit.get('files') != entries
                or not isinstance(commit.get('parents'), dict) or set(commit['parents']) != parents
                or any(not _identity(value) for value in commit['parents'].values())):
            raise ValueError('Quarantine commit evidence differs')
        phase = 'COMMIT_STARTED'
        for suffix, status in [('quarantined', 'QUARANTINED'), ('restore-intent', 'RESTORING'), ('restored', 'RESTORED')]:
            path = core._path('maintenance', identity, suffix)
            if path.exists() or path.is_symlink():
                record = core._read('maintenance', identity, suffix)
                if record.get('commit_intent_sha256') != _hash(commit):
                    raise ValueError('Quarantine disposition evidence differs')
                if suffix != 'restore-intent' and record.get('status') != status:
                    raise ValueError('Quarantine disposition status differs')
                if suffix == 'restored' and phase != 'RESTORING':
                    raise ValueError('Quarantine restore intent missing')
                phase = status
    cancelled_path = core._path('maintenance', identity, 'preparation-cancelled')
    if cancelled_path.exists() or cancelled_path.is_symlink():
        cancelled = core._read('maintenance', identity, 'preparation-cancelled')
        if (commit is not None or cancelled.get('status') != 'CANCELLED'
                or cancelled.get('operation_sha256') != _hash(operation)
                or cancelled.get('source_removal_executed') is not False):
            raise ValueError('Quarantine cancellation evidence differs')
        phase = 'CANCELLED'
    return root, expected, intents, phase


def _inspect(core, operation):
    from quarantine_locations import has_projection
    historical = operation.get('storage') != core.paths.binding()
    projected = historical or has_projection(core, operation)
    purge = core._path('maintenance', operation['id'], 'purge-intent')
    if (purge.exists() or purge.is_symlink()) and not projected:
        from purge_observations import inspect
        return inspect(core, operation)
    root, expected, intents, phase = _authority(core, operation, historical=historical)
    directory_identity = operation['directory_identity']
    if projected:
        from quarantine_locations import resolve
        root, location = resolve(core, operation)
        directory_identity = location['directory_identity']
        observed_ids = {item['path']: item['file_identity'] for item in location['files']}
        intents = {name: {**intent, 'file_identity': observed_ids.get(name)} for name, intent in intents.items()}
    purged_names = []; purge_plan = None
    expected_count, expected_bytes = len(expected), sum(item['size_bytes'] for item in expected.values())
    if projected and (purge.exists() or purge.is_symlink()):
        from purge_observations import context
        _, purge_plan, phase = context(core, operation['id'], relocated=True)
        if phase != 'PURGED':
            raise ValueError('Historical quarantine purge is not complete')
        purged_names = sorted(expected)
        expected, intents = {}, {}
    row = {'id': operation['id'], 'path': str(root), 'phase': phase,
           'files': operation['files'],
           'expected_file_count': expected_count, 'expected_logical_bytes': expected_bytes,
           'observed_logical_bytes': None, 'extra_files': [], 'missing_files': [],
           'changed_files': [], 'identity_conflicts': [], 'unregistered_payloads': [], 'unsafe_links': [],
           'source_removal_executed': (True if phase in ('QUARANTINED', 'PURGED') else
               None if phase in ('COMMIT_STARTED', 'RESTORING') else False)}
    if purge_plan is not None:
        row['purge_plan'] = purge_plan
    if root.resolve() != root or root.is_symlink():
        return {**row, 'status': 'UNSAFE'}, {}
    if not root.exists():
        return {**row, 'status': 'MISSING'}, {}
    info = root.stat()
    if not root.is_dir() or [info.st_dev, info.st_ino] != directory_identity:
        return {**row, 'status': 'IDENTITY_CONFLICT'}, {}
    files, links = files_without_links(root, strict=True)
    observed, inodes = {}, {}
    for path in files:
        name = path.relative_to(root).as_posix(); info = path.stat()
        observed[name] = {'sha256': digest(path), 'size_bytes': info.st_size,
                          'file_identity': [info.st_dev, info.st_ino]}
        inodes[(info.st_dev, info.st_ino)] = getattr(info, 'st_blocks', 0) * 512
    row['observed_logical_bytes'] = sum(item['size_bytes'] for item in observed.values())
    row['extra_files'] = sorted(set(observed) - set(expected))
    row['missing_files'] = sorted(set(expected) - set(observed))
    row['unsafe_links'] = sorted(path.relative_to(root).as_posix() for path in links)
    for name in sorted(set(observed) & set(expected)):
        if name not in intents:
            row['unregistered_payloads'].append(name)
        elif observed[name]['file_identity'] != intents[name]['file_identity']:
            row['identity_conflicts'].append(name)
        if any(observed[name][key] != expected[name][key] for key in ('sha256', 'size_bytes')):
            row['changed_files'].append(name)
    if row['identity_conflicts']:
        status = 'IDENTITY_CONFLICT'
    elif row['unregistered_payloads']:
        status = 'UNVERIFIED_OWNERSHIP'
    elif row['extra_files'] or row['unsafe_links']:
        status = 'CHANGED'
    elif row['missing_files'] or row['changed_files']:
        status = 'PARTIAL' if phase in ('PREPARING', 'INTERRUPTED') else 'CHANGED'
    else:
        status = 'VERIFIED'
    if phase == 'PURGED':
        row['purged_files'] = purged_names
        if status == 'VERIFIED':
            status = 'PURGED'
    return {**row, 'status': status}, inodes


def inventory(core):
    operations, unverified, inodes = [], [], {}
    records = core.paths.workspace / 'records/maintenance'
    if records.resolve() != records:
        raise ValueError('Quarantine maintenance records contain aliases')
    for path in sorted(records.glob('*.json')):
        try:
            operation = core._read('maintenance', path.stem)
            if operation.get('operation') != 'relocation-quarantine':
                continue
            row, blocks = _inspect(core, operation)
            operations.append(row); inodes.update(blocks)
        except (OSError, ValueError, KeyError, TypeError) as error:
            unverified.append({'id': path.stem, 'reason': str(error) or type(error).__name__})
    return {'operations': operations, 'unverified_operations': unverified,
            'capacity': {'observed_logical_bytes': sum(item['observed_logical_bytes'] or 0 for item in operations),
                         'unobserved_operation_count': sum(item['observed_logical_bytes'] is None for item in operations),
                         'unverified_operation_count': len(unverified), 'unique_file_inodes': len(inodes),
                         'allocated_bytes_estimate': sum(inodes.values()),
                         'estimate_caveat': 'Local stat blocks; shared extents and compression are not resolved'},
            'cleanup_executed': False, 'scope': 'Prepared relocation copies; content observations do not authorize source removal'}
