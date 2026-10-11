"""Read-only verification of retained reverse-relocation backup copies."""
import hashlib
from pathlib import Path, PurePosixPath
import re

from artifact_lifecycle import canonical, digest, overlaps
from inventory_lifecycle import files_without_links


def _hash(record):
    return hashlib.sha256(canonical(record)).hexdigest()


def _manifest(items):
    if not isinstance(items, list):
        raise ValueError('Backup manifest must be a list')
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Backup file record is invalid')
        name, sha, size = item.get('path'), item.get('sha256'), item.get('size_bytes')
        if (not isinstance(name, str) or not name or PurePosixPath(name).is_absolute()
                or '..' in PurePosixPath(name).parts or PurePosixPath(name).as_posix() != name
                or name in result or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
                or type(size) is not int or size < 0):
            raise ValueError('Backup file manifest scope is invalid')
        result[name] = item
    return result


def _verified_roots(core, plan):
    from reverse_relocation import _validate_intent
    identity = plan['id']
    if plan.get('config_path') != str(core.config_path):
        raise ValueError('Backup configuration authority differs')
    intent = core._read('relocations', identity, 'switch-intent')
    prepared = core._read('relocations', identity, 'prepared')
    switched = core._read('relocations', identity, 'switched')
    if (intent.get('plan_sha256') != _hash(plan) or intent.get('prepared_sha256') != _hash(prepared)
            or canonical(switched) != canonical(intent.get('receipt'))
            or intent.get('roots') != prepared.get('exchange_roots')):
        raise ValueError('Backup operation evidence differs')
    _validate_intent(core, plan, intent)
    _, groups, staging = core._relocation_layout(plan)
    if (prepared.get('staging') != staging or not isinstance(intent['roots'], list)
            or len(intent['roots']) != len(groups)
            or {root['group'] for root in intent['roots']} != set(groups)):
        raise ValueError('Backup layout differs from plan')
    copies = []
    for root in intent['roots']:
        key = root['group']
        expected = plan['occupied_root_identities'][key]
        if (root.get('staging') != staging[key] or root.get('destination') != str(groups[key])
                or root.get('destination_identity') != expected
                or root.get('operation') != ('PUBLISH' if expected is None else 'EXCHANGE')):
            raise ValueError('Backup root differs from plan')
        if expected is None:
            continue
        if not isinstance(expected, list) or len(expected) != 2 or any(type(value) is not int or value < 0 for value in expected):
            raise ValueError('Backup directory identity is invalid')
        manifest = _manifest(intent['backup_files'][key])
        copies.append((root, manifest))
    return copies


def _inspect(core, plan_id, root, manifest, displaced=None, report_dispositions=False):
    path = Path(root['staging'])
    item = {'relocation_id': plan_id, 'group': root['group'], 'path': str(path),
            'expected_directory_identity': root['destination_identity'], 'kind': root.get('kind', 'reverse-backup'),
            'expected_file_count': len(manifest),
            'expected_logical_bytes': sum(entry['size_bytes'] for entry in manifest.values()),
            'observed_logical_bytes': None, 'extra_files': [], 'missing_files': [],
            'changed_files': [], 'unsafe_links': []}
    if path.resolve() != path or path.is_symlink():
        return {**item, 'status': 'UNSAFE'}, {}
    if not path.exists():
        return {**item, 'status': 'MISSING'}, {}
    if not path.is_dir():
        return {**item, 'status': 'IDENTITY_CONFLICT'}, {}
    info = path.stat()
    if [info.st_dev, info.st_ino] != root['destination_identity']:
        return {**item, 'status': 'IDENTITY_CONFLICT'}, {}
    if any(overlaps(path, Path(location)) for location in core.paths.binding().values()):
        return {**item, 'status': 'ACTIVE_CONFLICT'}, {}
    files, links = files_without_links(path, strict=True)
    observed, inodes = {}, {}
    for file in files:
        name = file.relative_to(path).as_posix()
        stat = file.stat()
        observed[name] = {'size_bytes': stat.st_size, 'sha256': digest(file)}
        inodes[(stat.st_dev, stat.st_ino)] = getattr(stat, 'st_blocks', 0) * 512
    quarantined, purged = [], []
    for entry in displaced or []:
        source, retained = Path(entry['source']['path']), Path(entry['retained_path'])
        if not source.is_relative_to(path) or not retained.is_relative_to(path):
            continue
        name, moved_name = source.relative_to(path).as_posix(), retained.relative_to(path).as_posix()
        if entry.get('purged'):
            if name not in observed and moved_name not in observed and name in manifest:
                if report_dispositions:
                    purged.append({'relative_path': name, 'operation_id': entry['operation_id'],
                                   'sha256': entry['source']['sha256'], 'size_bytes': entry['source']['size_bytes']})
            continue
        if name in observed or moved_name not in observed:
            continue
        expected = entry['source']
        info = retained.stat()
        if (observed[moved_name] == {key: expected[key] for key in ('sha256', 'size_bytes')}
                and [info.st_dev, info.st_ino] == expected['file_identity']):
            observed[name] = observed.pop(moved_name)
            if report_dispositions:
                quarantined.append({'relative_path': name, 'retained_path': str(retained),
                    'operation_id': entry['operation_id'], 'sha256': expected['sha256'],
                    'size_bytes': expected['size_bytes']})
    controls = root.get('control_files', {})
    allowed = {name for name, expected in controls.items() if observed.get(name) == expected}
    item['verified_added_controls'] = sorted(allowed)
    item.update(observed_logical_bytes=sum(entry['size_bytes'] for entry in observed.values()),
                extra_files=sorted(set(observed) - set(manifest) - allowed),
                missing_files=sorted(set(manifest) - set(observed) - {entry['relative_path'] for entry in purged}),
                changed_files=sorted(name for name in set(observed) & set(manifest)
                    if any(observed[name][field] != manifest[name][field] for field in ('sha256', 'size_bytes'))),
                unsafe_links=sorted(link.relative_to(path).as_posix() for link in links))
    item['status'] = 'CHANGED' if any(item[field] for field in ('extra_files', 'missing_files', 'changed_files', 'unsafe_links')) else 'VERIFIED'
    if quarantined:
        item['quarantined_files'] = quarantined
        if item['status'] == 'VERIFIED':
            item['status'] = 'QUARANTINED'
    if purged:
        item['purged_files'] = purged
        if item['status'] in ('VERIFIED', 'QUARANTINED'):
            item['status'] = 'PARTIALLY_PURGED' if quarantined else 'PURGED'
    return item, inodes


def inventory(core, displaced=None):
    report_dispositions = displaced is None
    disposition_errors = []
    if report_dispositions:
        from source_dispositions import views
        displaced, disposition_errors = views(core)
    copies, unverified, inodes, staging = [], [], {}, []
    paths = core.paths.workspace / 'records/relocations'
    if paths.resolve() != paths:
        raise ValueError('Relocation inventory records contain aliases')
    for path in sorted(paths.glob('*.json')):
        identity = path.stem
        try:
            plan = core._read('relocations', identity)
            if plan.get('operation') not in ('relocation-plan', 'reverse-relocation-plan'):
                continue
            switched = core._path('relocations', identity, 'switched')
            if not switched.exists() and not switched.is_symlink():
                from staging_inventory import inspect
                rows, blocks = inspect(core, plan)
                staging.extend(rows); inodes.update(blocks)
                continue
            if plan['operation'] == 'relocation-plan':
                from forward_source_copies import verify
                roots = verify(core, plan)
            else:
                roots = _verified_roots(core, plan)
            for root, manifest in roots:
                item, blocks = _inspect(core, identity, root, manifest, displaced, report_dispositions)
                copies.append(item); inodes.update(blocks)
        except (ValueError, OSError, KeyError, TypeError) as error:
            unverified.append({'relocation_id': identity, 'reason': str(error) or type(error).__name__})
    observed = copies + staging
    result = {'copies': copies, 'staging': staging, 'unverified_operations': unverified,
            'capacity': {'observed_logical_bytes': sum(item['observed_logical_bytes'] or 0 for item in observed),
                         'unobserved_copy_count': sum(item['observed_logical_bytes'] is None for item in observed),
                         'unverified_operation_count': len(unverified),
                         'unique_file_inodes': len(inodes),
                         'allocated_bytes_estimate': sum(inodes.values()),
                         'estimate_caveat': 'Local stat blocks; shared extents and compression are not resolved'},
            'cleanup_executed': False,
            'scope': 'Retained sources, reverse backups and operation-bound staging; observations do not authorize cleanup'}

    if disposition_errors:
        result['disposition_errors'] = disposition_errors
        result['capacity']['unverified_disposition_count'] = len(disposition_errors)
    return result
