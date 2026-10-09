"""Read-only staging and pending-root observations from preparation evidence."""
from pathlib import Path
import hashlib

from artifact_lifecycle import canonical


def _record(core, identity, suffix):
    path = core._path('relocations', identity, suffix)
    return core._read('relocations', identity, suffix) if path.exists() or path.is_symlink() else None


def inspect(core, plan):
    from relocation_inventory import _inspect, _manifest, _hash
    from reverse_relocation import _identity, _locations, _validate_intent
    identity = plan['id']
    if plan.get('config_path') != str(core.config_path):
        raise ValueError('Staging configuration authority differs')
    intent = _record(core, identity, 'prepare-intent')
    if intent is None:
        return [], {}
    changed, groups, staging = core._relocation_layout(plan)
    if intent.get('staging') != staging or intent.get('groups') != {key: str(path) for key, path in groups.items()}:
        raise ValueError('Staging preparation layout differs')
    prepared = _record(core, identity, 'prepared')
    if prepared is not None:
        core._verify_staging_root_proofs(prepared)
    failure = _record(core, identity, 'prepare-outcome')
    cancelled = _record(core, identity, 'cancelled')
    switch = _record(core, identity, 'switch-intent')
    rollback = _record(core, identity, 'rollback')
    phase = 'PREPARING'
    for record in (failure, prepared, switch, rollback, cancelled):
        if record is not None:
            phase = 'SWITCH_INTERRUPTED' if record is switch else record['status']
    manifests = {key: [] for key in groups}
    for item in plan['files']:
        if item['root'] not in changed:
            continue
        _manifest([item])
        final = changed[item['root']] / item['path']
        key = next(key for key, root in groups.items() if final.is_relative_to(root))
        manifests[key].append({**item, 'path': final.relative_to(groups[key]).as_posix()})
    locations = {key: Path(path) for key, path in staging.items()}
    backups = {}
    if switch is not None:
        core._verified_relocation_controls(plan, switch)
        if plan['operation'] == 'reverse-relocation-plan':
            _validate_intent(core, plan, switch)
            if (prepared is None or switch['prepared_sha256'] != _hash(prepared)
                    or switch['roots'] != prepared['exchange_roots']):
                raise ValueError('Staging reverse root journal differs')
            locations, backups = _locations(switch['roots'])
    rows, inodes = [], {}
    for key, stage in staging.items():
        marker_data = canonical({'plan_id': identity, 'group': key})
        manifests[key].append({'path': '.relocation-owner.json', 'size_bytes': len(marker_data),
                               'sha256': hashlib.sha256(marker_data).hexdigest()})
        expected = _manifest(manifests[key])
        proof = _record(core, identity, 'staging-root-' + key)
        root = locations[key]
        if proof is None:
            rows.append({'relocation_id': identity, 'group': key, 'path': str(root), 'kind': 'staging',
                         'phase': phase, 'status': 'UNVERIFIED_OWNERSHIP', 'observed_logical_bytes': None,
                         'extra_files': [], 'missing_files': [], 'changed_files': [], 'unsafe_links': []})
            continue
        directory_identity = proof.get('directory_identity')
        if (proof.get('group') != key or proof.get('path') != stage
                or not isinstance(directory_identity, list) or len(directory_identity) != 2
                or any(type(value) is not int or value < 0 for value in directory_identity)):
            raise ValueError('Staging directory identity proof differs')
        if switch is not None and plan['operation'] == 'relocation-plan' and not root.exists() and not root.is_symlink():
            if groups[key].exists() or groups[key].is_symlink():
                root = groups[key]
        descriptor = {'group': key, 'staging': str(root), 'destination_identity': directory_identity,
                      'kind': 'staging' if root == Path(stage) else 'pending-target'}
        if root.resolve() == root and root.is_dir() and _identity(root) == directory_identity:
            marker = root / '.relocation-owner.json'
            if marker.resolve() != marker or not marker.is_file() or marker.read_bytes() != marker_data:
                rows.append({'relocation_id': identity, 'group': key, 'path': str(root), 'kind': descriptor['kind'],
                             'phase': phase, 'status': 'UNVERIFIED_OWNERSHIP', 'observed_logical_bytes': None,
                             'extra_files': [], 'missing_files': [], 'changed_files': [], 'unsafe_links': []})
                continue
        row, blocks = _inspect(core, identity, descriptor, expected)
        row['phase'] = phase
        if row['status'] == 'CHANGED' and row['missing_files'] and not any(row[field] for field in ('extra_files', 'changed_files', 'unsafe_links')):
            row['status'] = 'PARTIAL'
        rows.append(row); inodes.update(blocks)
        if key in backups and backups[key] is not None:
            old = next(entry for entry in switch['roots'] if entry['group'] == key)
            descriptor = {'group': key, 'staging': str(backups[key]), 'destination_identity': old['destination_identity'],
                          'kind': 'pending-backup'}
            row, blocks = _inspect(core, identity, descriptor, _manifest(switch['backup_files'][key]))
            row['phase'] = phase; rows.append(row); inodes.update(blocks)
    return rows, inodes
