"""Journaled reverse root exchange with explicit source recovery."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from inventory_lifecycle import files_without_links


def _configuration_authority(core, plan):
    from configuration_layers import owning_document
    return owning_document(core.paths.project, core.config_path, plan['configuration_change'])


def _configuration_target(core, plan):
    return _configuration_authority(core, plan)['path']


def _hash(value):
    from artifact_lifecycle import canonical
    return hashlib.sha256(canonical(value)).hexdigest()


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_ancestors(path, workspace):
    while path.is_relative_to(workspace):
        _sync(path)
        if path == workspace:
            _sync(path.parent)
            return
        path = path.parent
    raise ValueError('Reverse journal sync escapes source workspace')


def _sync_tree(root):
    directories = [root]
    for path in root.rglob('*'):
        if path.resolve() != path or path.is_symlink():
            raise ValueError('Reverse staging tree contains aliases')
        if path.is_dir():
            directories.append(path)
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        _sync(directory)


def _tree(path):
    from artifact_lifecycle import digest
    files, links = files_without_links(path, strict=True)
    if links:
        raise ValueError('Reverse backup contains unsafe links')
    return sorted([{'path': item.relative_to(path).as_posix(), 'sha256': digest(item),
                    'size_bytes': item.stat().st_size} for item in files], key=lambda item: item['path'])


def _persist(core, path, record):
    from artifact_lifecycle import canonical
    if path.resolve() != path:
        raise ValueError('Reverse control path contains aliases')
    if path.exists() or path.is_symlink():
        if path.resolve() != path or not path.is_file() or path.read_bytes() != canonical(record):
            raise ValueError('Reverse relocation immutable control evidence differs')
    else:
        core._write_path(path, record)
    _sync(path.parent)


def _identity(path):
    if path.resolve() != path or path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError('Reverse root identity location changed')
    if not path.exists():
        return None
    info = path.stat()
    return [info.st_dev, info.st_ino]


def _locations(roots):
    locations = {}
    backups = {}
    for root in roots:
        staged, final = Path(root['staging']), Path(root['destination'])
        pair = (_identity(staged), _identity(final))
        before = (root['staging_identity'], root['destination_identity'])
        after = (root['destination_identity'], root['staging_identity'])
        if pair == before:
            locations[root['group']] = staged
            backups[root['group']] = final if root['operation'] == 'EXCHANGE' else None
        elif pair == after:
            locations[root['group']] = final
            backups[root['group']] = staged if root['operation'] == 'EXCHANGE' else None
        else:
            raise ValueError('Reverse directory identity differs from journal')
    return locations, backups


def _validate_intent(core, plan, intent):
    from artifact_lifecycle import Lifecycle, canonical
    if _configuration_target(core, plan) == core.config_path:
        core._assert_relocation_local_absence()
    core._verify_staging_root_proofs(core._read('relocations', plan['id'], 'prepared'))
    target_config = intent.get('target_config')
    if not isinstance(target_config, dict) or _hash(target_config) != plan['target_config_sha256']:
        raise ValueError('Reverse target configuration differs from approved plan')
    target = Lifecycle(core.paths.project, target_config, core.config_path)
    if target.paths.binding() != plan['to']:
        raise ValueError('Reverse target configuration storage scope differs')
    target._assert_paths()
    source = base64.b64decode(intent['source_config_base64'], validate=True)
    if (source != _configuration_authority(core, plan)['source_bytes']
            or hashlib.sha256(source).hexdigest() != plan['source_config_file_sha256']
            or _hash(_configuration_authority(core, plan)['source_effective_config']) != plan['source_config_sha256']):
        raise ValueError('Reverse source configuration backup differs from plan')
    receipt = intent.get('receipt')
    required = {'id': plan['id'], 'status': 'SWITCHED', 'from': plan['from'], 'to': plan['to'],
                'reverse_of': plan['forward_id'], 'config_path': str(core.config_path),
                'project_id': core.config.get('project', {}).get('id'),
                'preserved_backups': [root['staging'] for root in intent['roots'] if root['operation'] == 'EXCHANGE']}
    if (not isinstance(receipt, dict) or type(receipt.get('schema_version')) is not int
            or receipt['schema_version'] != 1 or receipt.get('source_deleted') is not False
            or any(canonical(receipt.get(key)) != canonical(value) for key, value in required.items())
            or any(not isinstance(receipt.get(key), str) or not receipt[key].strip()
                   for key in ('actor', 'reason', 'created_at'))):
        raise ValueError('Reverse switch receipt scope differs from plan')
    if receipt.get('backup_quarantine_locations_sha256') != _hash(intent.get('backup_quarantine_locations', {})):
        raise ValueError('Backup quarantine location proof binding differs')
    core._verified_relocation_controls(plan, intent)
    source_key, target_key = _hash(plan['from']), _hash(plan['to'])
    common = {'schema_version': 1, 'created_at': receipt['created_at']}
    expected = {
        'activation': {**common, 'id': target_key, 'to': plan['to'],
                       'relocation_id': plan['id'], 'switch_sha256': _hash(receipt)},
        'edge': {**common, 'id': source_key, 'from': plan['from'], 'to': plan['to'],
                 'relocation_id': plan['id'], 'switch_sha256': _hash(receipt)},
        'release': {**common, 'id': target_key, 'reverse_id': plan['id'], 'forward_id': plan['forward_id'],
                    'fence_sha256': _hash(core._read('storage-fences', target_key, plan['forward_id'])),
                    'reverse_switch_sha256': _hash(receipt)}}
    if any(canonical(intent.get(key)) != canonical(value) for key, value in expected.items()):
        raise ValueError('Reverse control evidence differs from plan')


def _target_workspace(plan, roots, locations):
    workspace = Path(plan['to']['workspace'])
    group = next((root for root in roots if workspace.is_relative_to(Path(root['destination']))), None)
    if group is not None:
        workspace = locations[group['group']] / workspace.relative_to(Path(group['destination']))
    return workspace, group


def _control_paths(intent, workspace):
    return {workspace / 'records' / category / (change['key'] + '.json'): change
            for category, change in intent['storage_controls'].items()}


def _verify_staged(core, plan, intent, prepared, locations):
    from artifact_lifecycle import canonical, digest
    workspace, _ = _target_workspace(plan, intent['roots'], locations)
    from quarantine_locations import verify_at
    verify_at(core, prepared, workspace)
    controls = _control_paths(intent, workspace)
    for item in prepared['staged_files']:
        original = Path(item['path'])
        root = next(root for root in intent['roots'] if original.is_relative_to(Path(root['staging'])))
        current = locations[root['group']] / original.relative_to(Path(root['staging']))
        if current.resolve() != current or not current.is_file():
            raise ValueError('Reverse relocation staged integrity failure')
        if current in controls and current.read_bytes() == canonical(controls[current]['after']):
            continue
        if current.stat().st_size != item['size_bytes'] or digest(current) != item['sha256']:
            raise ValueError('Reverse relocation staged integrity failure')


def _verify_configuration_state(core, plan, intent):
    from artifact_lifecycle import canonical
    from configuration_preparation import verify_prepared_storage_change, _RelocationConfigurationCore
    from configuration_installation import verify_configuration_installation
    prepared = core._read('relocations', plan['id'], 'configuration-prepared')
    if prepared != intent.get('configuration_prepared'):
        raise ValueError('Reverse configuration preparation receipt differs')
    source = base64.b64decode(intent['source_config_base64'], validate=True)
    target = _configuration_authority(core, plan)['target_bytes']
    if _configuration_target(core, plan).is_symlink() or not _configuration_target(core, plan).is_file():
        raise ValueError('Reverse configuration location changed')
    actual = _configuration_target(core, plan).read_bytes()
    if actual == source:
        verify_prepared_storage_change(_RelocationConfigurationCore(core), plan['configuration_change'], plan['id'])
        installation = core._path('relocations', plan['id'], 'configuration-installation')
        if installation.exists() or installation.is_symlink():
            verify_configuration_installation(core, plan['id'])
    elif actual == target:
        verify_configuration_installation(core, plan['id'], installed=True)
    else:
        raise ValueError('Reverse configuration was edited; refusing overwrite')
    return actual


def _execute(core, plan, intent):
    from artifact_lifecycle import Lifecycle, canonical, digest
    import delivery_lifecycle
    from storage_control_projection import publish
    _validate_intent(core, plan, intent)
    _verify_configuration_state(core, plan, intent)
    if (intent.get('plan_sha256') != _hash(plan)
            or intent.get('prepared_sha256') != _hash(core._read('relocations', plan['id'], 'prepared'))
            or plan['from'] != core.paths.binding() or intent['receipt']['to'] != plan['to']):
        raise ValueError('Reverse relocation journal scope changed')
    prepared = core._read('relocations', plan['id'], 'prepared')
    if intent['roots'] != prepared['exchange_roots']:
        raise ValueError('Reverse relocation root journal changed')
    source_key = _hash(plan['from']); target_key = _hash(plan['to'])
    fence = core._read('storage-fences', source_key, plan['id'])
    if _hash(fence) != intent['fence_sha256']:
        raise ValueError('Reverse relocation source fence differs')
    owned = {core._path('storage-fences', source_key, plan['id']).relative_to(core.paths.workspace).as_posix()}
    if plan['from']['workspace'] == plan['to']['workspace']:
        owned.update({'records/storage-activations/' + target_key + '.json',
                      'records/storage-bindings/' + source_key + '.json',
                      'records/storage-fence-releases/' + target_key + '/' + plan['forward_id'] + '.json'})
    source_files, _ = core._relocation_file_snapshot()
    source_files = [item for item in source_files if not (item['root'] == 'workspace' and item['path'] in owned)]
    expected_files = [item for item in plan['files'] if not (item['root'] == 'workspace' and item['path'] in owned)]
    if source_files != expected_files:
        raise ValueError('Reverse relocation source data changed after fencing')
    locations, backups = _locations(intent['roots'])
    from quarantine_locations import verify_backup
    for key, path in backups.items():
        if path is not None:
            verify_backup(plan, intent, key, path)
        if path is not None and _tree(path) != intent['backup_files'][key]:
            raise ValueError('Reverse relocation preserved backup bytes changed')
    _verify_staged(core, plan, intent, prepared, locations)
    target_workspace, workspace_group = _target_workspace(plan, intent['roots'], locations)
    source_records = core.paths.workspace / 'records'
    target_records = target_workspace / 'records'
    files, links = files_without_links(source_records)
    if links:
        raise ValueError('Reverse relocation source records contain links')
    if source_records != target_records:
        controlled = set(_control_paths(intent, target_workspace))
        for source in files:
            destination = target_records / source.relative_to(source_records)
            if destination not in controlled:
                _persist(core, destination, json.loads(source.read_text()))
    change = intent['storage_controls']['storage-activations']
    publish(core, target_workspace, plan['id'], 'storage-activations', change['key'], change['before'], change['after'])
    for location in locations.values():
        _sync_tree(location)
    if workspace_group is None:
        _sync_tree(target_records)
    for root in intent['roots']:
        delivery_lifecycle.apply_directory_change(root)
    target = Lifecycle(core.paths.project, intent['target_config'], core.config_path)
    target._assert_paths()
    transformed = _control_paths(intent, target.paths.workspace)
    for item in plan['files']:
        path = Path(plan['to'][item['root']]) / item['path']
        if path.resolve() != path or not path.is_file():
            raise ValueError('Reverse relocation published bytes differ')
        if path in transformed and path.read_bytes() == canonical(transformed[path]['after']):
            continue
        if path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
            raise ValueError('Reverse relocation published bytes differ')
    source_config = base64.b64decode(intent['source_config_base64'], validate=True)
    target_config = _configuration_authority(core, plan)['target_bytes']
    if hashlib.sha256(source_config).hexdigest() != plan['source_config_file_sha256']:
        raise ValueError('Reverse source configuration backup differs')
    if _configuration_target(core, plan).is_symlink() or not _configuration_target(core, plan).is_file():
        raise ValueError('Reverse configuration location changed')
    actual = _verify_configuration_state(core, plan, intent)
    target_records = target.paths.workspace / 'records'
    change = intent['storage_controls']['storage-bindings']
    publish(core, target.paths.workspace, plan['id'], 'storage-bindings', change['key'], change['before'], change['after'])
    _persist(core, target_records / 'storage-fence-releases' / target_key / (plan['forward_id'] + '.json'), intent['release'])
    if actual != target_config:
        from configuration_installation import prepare_configuration_installation
        temporary = prepare_configuration_installation(core, plan['id'])
        _verify_configuration_state(core, plan, intent)
        os.replace(temporary, _configuration_target(core, plan))
    from configuration_installation import verify_configuration_installation, transfer_installation_proof
    verify_configuration_installation(core, plan['id'], installed=True)
    core._sync_configuration_directory()
    transfer_installation_proof(core, plan['id'], target.paths.workspace)
    _persist(core, target_records / 'relocations' / plan['id'] / 'switched.json', intent['receipt'])
    if target_records != source_records:
        _persist(core, core._path('relocations', plan['id'], 'switched'), intent['receipt'])
    return intent['receipt']


def record_interruption(core, plan_id, error):
    """Preserve the initial failure without masking an execution exception."""
    try:
        completed = core._path('relocations', plan_id, 'switched')
        if completed.exists() or completed.is_symlink():
            if core._read('relocations', plan_id, 'switched').get('status') == 'SWITCHED':
                return
        path = core._path('relocations', plan_id, 'switch-intent')
        if not path.exists() and not path.is_symlink():
            return
        core._read('relocations', plan_id, 'switch-intent')
        outcome = core._path('relocations', plan_id, 'switch-outcome')
        if not outcome.exists() and not outcome.is_symlink():
            core._record('relocations', {'id': plan_id, 'status': 'SWITCH_INTERRUPTED',
                'reason': str(error) or type(error).__name__, 'source_deleted': False}, 'switch-outcome')
        _sync_ancestors(outcome.parent, core.paths.workspace)
    except BaseException as persistence_error:
        error.add_note('Could not persist reverse interruption evidence: ' + str(persistence_error))


def switch(core, plan_id, actor, reason):
    from artifact_lifecycle import canonical, now
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('Reverse switch requires actor and reason')
    with core.transaction():
        core._verify_reverse_relocation_locked(plan_id)
        plan = core._read('relocations', plan_id)
        prepared = core._read('relocations', plan_id, 'prepared')
        core._verify_prepared_relocation(prepared)
        if core._path('relocations', plan_id, 'switch-intent').exists():
            raise ValueError('Reverse switch already started; use explicit recovery')
        authority = _configuration_authority(core, plan)
        target_config = authority['effective_config']
        from configuration_preparation import prepare_storage_change, _RelocationConfigurationCore
        configuration_prepared = prepare_storage_change(_RelocationConfigurationCore(core),
            plan['configuration_change'], plan_id, actor, reason)
        if Path(configuration_prepared['staged_path']).read_bytes() != authority['target_bytes']:
            raise ValueError('Reverse prepared configuration differs from target')
        receipt = {'schema_version': 1, 'id': plan_id, 'created_at': now(), 'status': 'SWITCHED',
                   'from': plan['from'], 'to': plan['to'], 'reverse_of': plan['forward_id'],
                   'config_path': str(core.config_path), 'project_id': core.config.get('project', {}).get('id'),
                   'actor': actor, 'reason': reason, 'source_deleted': False,
                   'preserved_backups': [root['staging'] for root in prepared['exchange_roots'] if root['operation'] == 'EXCHANGE']}
        from quarantine_locations import capture_backups
        backup_locations = capture_backups(plan, prepared)
        receipt['backup_quarantine_locations_sha256'] = _hash(backup_locations)
        source_key, target_key = _hash(plan['from']), _hash(plan['to'])
        forward_fence = core._read('storage-fences', target_key, plan['forward_id'])
        common = {'schema_version': 1, 'created_at': receipt['created_at']}
        activation = {**common, 'id': target_key, 'to': plan['to'], 'relocation_id': plan_id, 'switch_sha256': _hash(receipt)}
        edge = {**common, 'id': source_key, 'from': plan['from'], 'to': plan['to'], 'relocation_id': plan_id, 'switch_sha256': _hash(receipt)}
        release = {**common, 'id': target_key, 'reverse_id': plan_id, 'forward_id': plan['forward_id'],
                   'fence_sha256': _hash(forward_fence), 'reverse_switch_sha256': _hash(receipt)}
        backup_files = {root['group']: _tree(Path(root['destination'])) for root in prepared['exchange_roots'] if root['operation'] == 'EXCHANGE'}
        changes = core._relocation_control_changes(plan, receipt)
        intent = {'id': plan_id, 'actor': actor, 'reason': reason, 'plan_sha256': _hash(plan),
                  'storage_controls': changes, 'configuration_prepared': configuration_prepared,
                  'prepared_sha256': _hash(prepared), 'roots': prepared['exchange_roots'],
                  'backup_files': backup_files, 'backup_quarantine_locations': backup_locations, 'target_config': target_config,
                  'source_config_base64': base64.b64encode(_configuration_target(core, plan).read_bytes()).decode('ascii'),
                  'source_config_mode': _configuration_target(core, plan).stat().st_mode & 0o777,
                  'receipt': receipt, 'activation': activation, 'edge': edge, 'release': release}
        # Persist the intent before fencing or changing any directory.
        stored = core._record('relocations', intent, 'switch-intent')
        _sync_ancestors(core._path('relocations', plan_id, 'switch-intent').parent, core.paths.workspace)
        fence = core._fence_relocation_locked(plan_id)
        stored['fence_sha256'] = _hash(fence)
        core._record('relocations', {'id': plan_id, 'fence_sha256': stored['fence_sha256']}, 'reverse-fence')
        _sync_ancestors(core._path('storage-fences', source_key, plan_id).parent, core.paths.workspace)
        _sync_ancestors(core._path('relocations', plan_id, 'reverse-fence').parent, core.paths.workspace)
        return _execute(core, plan, stored)


def resume(core, plan_id, actor, reason):
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('Reverse recovery requires actor and reason')
    from relocation_lifecycle import recovery_lock
    with recovery_lock(core):
        plan = core._read('relocations', plan_id)
        if plan.get('operation') != 'reverse-relocation-plan' or plan['from'] != core.paths.binding():
            raise ValueError('Reverse recovery source scope changed')
        intent = core._read('relocations', plan_id, 'switch-intent')
        _validate_intent(core, plan, intent)
        rollback_path = core._path('relocations', plan_id, 'rollback-intent')
        if rollback_path.exists() or rollback_path.is_symlink():
            core._read('relocations', plan_id, 'rollback-intent')
            raise ValueError('Reverse rollback already started; continue rollback')
        completed = core._path('relocations', plan_id, 'switched')
        if completed.exists() or completed.is_symlink():
            from artifact_lifecycle import Lifecycle
            receipt = core._read('relocations', plan_id, 'switched')
            target = Lifecycle(core.paths.project, intent['target_config'], core.config_path)
            if receipt != intent['receipt'] or target._read('relocations', plan_id, 'switched') != receipt:
                raise ValueError('Completed reverse switch receipt differs')
            target._check_storage_activation()
            target._check_storage_write_fence()
            status = core.relocation_status(plan_id)
            if status['target_activation_status'] != 'VERIFIED':
                raise ValueError('Completed reverse resume target control activation verification failed: ' + '; '.join(status['target_activation_errors']))
            return receipt
        _verify_configuration_state(core, plan, intent)
        source_key = _hash(plan['from'])
        fence_path = core._path('storage-fences', source_key, plan_id)
        if not fence_path.exists() and not fence_path.is_symlink():
            core._verify_reverse_relocation_locked(plan_id)
            core._verify_prepared_relocation(core._read('relocations', plan_id, 'prepared'))
            core._fence_relocation_locked(plan_id)
        fence = core._read('storage-fences', source_key, plan_id)
        if (fence.get('from') != plan['from'] or fence.get('relocation_id') != plan_id
                or fence.get('config_path') != str(core.config_path)
                or fence.get('project_id') != core.config.get('project', {}).get('id')
                or fence.get('prepared_sha256') != intent['prepared_sha256']):
            raise ValueError('Reverse recovery fence scope changed')
        proof_path = core._path('relocations', plan_id, 'reverse-fence')
        if not proof_path.exists() and not proof_path.is_symlink():
            core._record('relocations', {'id': plan_id, 'fence_sha256': _hash(fence)}, 'reverse-fence')
        intent['fence_sha256'] = core._read('relocations', plan_id, 'reverse-fence')['fence_sha256']
        _sync_ancestors(core._path('relocations', plan_id, 'switch-intent').parent, core.paths.workspace)
        _sync_ancestors(fence_path.parent, core.paths.workspace)
        _sync_ancestors(proof_path.parent, core.paths.workspace)
        return _execute(core, plan, intent)


def _verify_rollback_configuration_state(core, plan, intent):
    from artifact_lifecycle import canonical
    from configuration_layers import verify_storage_change, verify_local_git_protection
    from configuration_installation import installation_paths, verify_configuration_installation
    source = base64.b64decode(intent['source_config_base64'], validate=True)
    if _configuration_target(core, plan).is_symlink() or not _configuration_target(core, plan).is_file():
        raise ValueError('Reverse rollback configuration location changed')
    actual = _configuration_target(core, plan).read_bytes()
    _, temporary, restoration = installation_paths(core, plan['id'], restoring=True)
    for path in (temporary, restoration):
        verify_local_git_protection(path)
    if actual == source:
        if restoration.exists() or restoration.is_symlink():
            verify_configuration_installation(core, plan['id'], installed=True, restoring=True)
        else:
            verify_storage_change(core.paths.project, core.config_path, plan['configuration_change'])
    elif actual == _configuration_authority(core, plan)['target_bytes']:
        verify_configuration_installation(core, plan['id'], installed=True)
    else:
        raise ValueError('Reverse rollback configuration was edited; refusing overwrite')
    return actual


def rollback(core, plan_id, actor, reason):
    from artifact_lifecycle import canonical, digest
    from storage_control_projection import restore
    import delivery_lifecycle
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('Reverse rollback requires actor and reason')
    from relocation_lifecycle import recovery_lock
    with recovery_lock(core):
        plan = core._read('relocations', plan_id)
        if plan.get('operation') != 'reverse-relocation-plan' or plan['from'] != core.paths.binding():
            raise ValueError('Reverse rollback source scope changed')
        intent = core._read('relocations', plan_id, 'switch-intent')
        _validate_intent(core, plan, intent)
        source_key, target_key = _hash(plan['from']), _hash(plan['to'])
        release_path = core._path('storage-fence-releases', source_key, plan_id)
        if core._path('relocations', plan_id, 'rollback').exists() and release_path.exists():
            core._check_storage_write_fence()
            _sync_ancestors(release_path.parent, core.paths.workspace)
            return core._read('relocations', plan_id, 'rollback')
        switched = Path(plan['to']['workspace']) / 'records/relocations' / plan_id / 'switched.json'
        if switched.exists() or switched.is_symlink() or core._path('relocations', plan_id, 'switched').exists():
            raise ValueError('Activated reverse relocation cannot use interrupted rollback')
        _verify_rollback_configuration_state(core, plan, intent)
        prepared = core._read('relocations', plan_id, 'prepared')
        if (intent['plan_sha256'] != _hash(plan) or intent['prepared_sha256'] != _hash(prepared)
                or intent['roots'] != prepared['exchange_roots']):
            raise ValueError('Reverse rollback journal changed')
        fence_path = core._path('storage-fences', source_key, plan_id)
        if not fence_path.exists() and not fence_path.is_symlink():
            core._fence_relocation_locked(plan_id)
        fence = core._read('storage-fences', source_key, plan_id)
        if (fence.get('from') != plan['from'] or fence.get('relocation_id') != plan_id
                or fence.get('config_path') != str(core.config_path)
                or fence.get('project_id') != core.config.get('project', {}).get('id')
                or fence.get('prepared_sha256') != intent['prepared_sha256']):
            raise ValueError('Reverse rollback fence scope changed')
        proof_path = core._path('relocations', plan_id, 'reverse-fence')
        if proof_path.exists() or proof_path.is_symlink():
            if core._read('relocations', plan_id, 'reverse-fence').get('fence_sha256') != _hash(fence):
                raise ValueError('Reverse rollback fence hash differs')
        source = base64.b64decode(intent['source_config_base64'], validate=True)
        if _configuration_target(core, plan).is_symlink() or not _configuration_target(core, plan).is_file():
            raise ValueError('Reverse rollback configuration location changed')
        if _configuration_target(core, plan).read_bytes() not in (source, _configuration_authority(core, plan)['target_bytes']):
            raise ValueError('Reverse rollback configuration was edited; refusing overwrite')
        owned = {'records/storage-fences/' + source_key + '/' + plan_id + '.json'}
        shared = plan['from']['workspace'] == plan['to']['workspace']
        controls = {'activation': 'records/storage-activations/' + target_key + '.json',
                    'edge': 'records/storage-bindings/' + source_key + '.json',
                    'release': 'records/storage-fence-releases/' + target_key + '/' + plan['forward_id'] + '.json'}
        if shared:
            owned.update(controls.values())
        files, _ = core._relocation_file_snapshot()
        def filtered(items):
            return [item for item in items if not (item['root'] == 'workspace' and item['path'] in owned)]
        if filtered(files) != filtered(plan['files']):
            raise ValueError('Reverse rollback source data changed')
        locations, backups = _locations(intent['roots'])
        from quarantine_locations import verify_backup
        for key, backup in backups.items():
            if backup is not None:
                verify_backup(plan, intent, key, backup)
            if backup is not None and _tree(backup) != intent['backup_files'][key]:
                raise ValueError('Reverse rollback preserved backup changed')
        _verify_staged(core, plan, intent, prepared, locations)
        rollback_path = core._path('relocations', plan_id, 'rollback-intent')
        if not rollback_path.exists() and not rollback_path.is_symlink():
            core._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                'switch_intent_sha256': _hash(intent),
                'source_config_sha256': plan['source_config_file_sha256']}, 'rollback-intent')
        rollback_intent = core._read('relocations', plan_id, 'rollback-intent')
        if (rollback_intent['switch_intent_sha256'] != _hash(intent)
                or rollback_intent.get('source_config_sha256') != plan['source_config_file_sha256']):
            raise ValueError('Reverse rollback intent scope changed')
        _sync_ancestors(rollback_path.parent, core.paths.workspace)
        _sync_ancestors(fence_path.parent, core.paths.workspace)
        _verify_rollback_configuration_state(core, plan, intent)
        for root in reversed(intent['roots']):
            delivery_lifecycle.revert_directory_change(root)
        if shared:
            baseline = {item['path']: item for item in plan['files'] if item['root'] == 'workspace'}
            for name, relative in controls.items():
                path = core.paths.workspace / relative
                if name in ('activation', 'edge'):
                    category = 'storage-activations' if name == 'activation' else 'storage-bindings'
                    change = intent['storage_controls'][category]
                    retired = rollback_path.parent / 'retired-controls' / (name + '.json')
                    if path.exists() and path.resolve() == path and path.read_bytes() == canonical(change['after']):
                        _persist(core, retired, change['after'])
                        _sync_ancestors(retired.parent, core.paths.workspace)
                    restore(core, core.paths.workspace, plan_id, category, change['key'], change['before'], change['after'])
                    continue
                if relative in baseline:
                    if not path.is_file() or digest(path) != baseline[relative]['sha256']:
                        raise ValueError('Pre-existing reverse control evidence changed')
                    continue
                retired = rollback_path.parent / 'retired-controls' / (name + '.json')
                if path.exists() or path.is_symlink():
                    if path.resolve() != path or not path.is_file() or path.read_bytes() != canonical(intent[name]):
                        raise ValueError('Reverse pending control differs; refusing retirement')
                    _persist(core, retired, intent[name])
                    _sync_ancestors(retired.parent, core.paths.workspace)
                    path.unlink(); _sync(path.parent)
                elif retired.exists() or retired.is_symlink():
                    _persist(core, retired, intent[name])
        actual = _verify_rollback_configuration_state(core, plan, intent)
        if actual != source:
            from configuration_installation import prepare_configuration_installation, verify_configuration_installation
            temporary = prepare_configuration_installation(core, plan_id, restoring=True)
            _verify_rollback_configuration_state(core, plan, intent)
            os.replace(temporary, _configuration_target(core, plan))
            verify_configuration_installation(core, plan_id, installed=True, restoring=True)
        _verify_rollback_configuration_state(core, plan, intent)
        core._sync_configuration_directory()
        receipt_path = core._path('relocations', plan_id, 'rollback')
        if receipt_path.exists() or receipt_path.is_symlink():
            receipt = core._read('relocations', plan_id, 'rollback')
        else:
            receipt = core._record('relocations', {'id': plan_id, 'status': 'ROLLED_BACK',
                'from': plan['from'], 'to': plan['to'], 'actor': rollback_intent['actor'],
                'reason': rollback_intent['reason'], 'source_deleted': False,
                'preserved_staging': [root['staging'] for root in intent['roots']]}, 'rollback')
        _sync_ancestors(receipt_path.parent, core.paths.workspace)
        if not release_path.exists() and not release_path.is_symlink():
            core._record('storage-fence-releases', {'id': source_key,
                'fence_sha256': _hash(fence), 'rollback_sha256': _hash(receipt)}, plan_id)
        _sync_ancestors(release_path.parent, core.paths.workspace)
        core._check_storage_write_fence()
        return receipt
