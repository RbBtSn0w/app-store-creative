"""Read-only observations of intent-bound permanent removal."""
from pathlib import Path

from purge_execution import _context, _existing_checkpoint, _checkpoint, guard_view
from relocation_quarantine import _hash


def context(core, identity, relocated=False):
    intent = core._read('maintenance', identity, 'purge-intent')
    plan = core._read('maintenance', intent['plan_id'])
    if plan.get('quarantine_id') != identity or intent.get('plan_sha256') != _hash(plan):
        raise ValueError('Purge observation plan authority differs')
    historical = relocated or plan.get('storage') != core.paths.binding()
    operation = _context(core, plan, historical=historical)
    if not relocated:
        guard_view(core, plan)
    done = core._path('maintenance', identity, 'purged')
    phase = 'PURGING'
    if done.exists() or done.is_symlink():
        receipt = core._read('maintenance', identity, 'purged')
        if (receipt.get('status') != 'PURGED' or receipt.get('plan_id') != plan['id']
                or receipt.get('purge_intent_sha256') != _hash(intent)):
            raise ValueError('Purge observation receipt differs')
        for index, item in enumerate(plan['files']):
            if _existing_checkpoint(core, plan, index) is None:
                raise ValueError('Completed purge file intent missing')
            if relocated:
                continue
            tombstone = Path(_checkpoint(core, plan, index)['tombstone'])
            path = Path(item['path'])
            if path.exists() or path.is_symlink() or tombstone.exists() or tombstone.is_symlink():
                raise ValueError('Purged media reappeared')
        phase = 'PURGED'
    if relocated and phase != 'PURGED':
        raise ValueError('Relocated purge terminal receipt missing')
    return operation, plan, phase


def inspect(core, operation):
    operation, plan, phase = context(core, operation['id'])
    root = Path(operation['quarantine_root']); observed = 0; inodes = {}; removed = []
    for index, item in enumerate(plan['files']):
        if item['kind'] != 'prepared':
            continue
        path = Path(item['path']); checkpoint = _existing_checkpoint(core, plan, index)
        if not path.exists() and checkpoint:
            tombstone = Path(checkpoint['tombstone'])
            if tombstone.exists():
                path = tombstone
            else:
                removed.append(Path(item['path']).name); continue
        if path.is_file():
            info = path.stat(); observed += info.st_size
            inodes[(info.st_dev, info.st_ino)] = getattr(info, 'st_blocks', 0) * 512
    prepared_files = [item for item in plan['files'] if item['kind'] == 'prepared']
    return {'id': operation['id'], 'path': str(root), 'phase': phase, 'status': phase,
            'files': operation['files'], 'purge_plan': plan,
            'expected_file_count': len(prepared_files),
            'expected_logical_bytes': sum(item['size_bytes'] for item in prepared_files),
            'observed_logical_bytes': observed, 'extra_files': [], 'missing_files': [], 'changed_files': [],
            'identity_conflicts': [], 'unregistered_payloads': [], 'unsafe_links': [],
            'purged_files': sorted(removed), 'source_removal_executed': True}, inodes


def source_entries(core, identity):
    from quarantine_locations import has_projection
    operation = core._read('maintenance', identity)
    projected = operation.get('storage') != core.paths.binding() or has_projection(core, operation)
    operation, plan, phase = context(core, identity, relocated=projected)
    entries = []; index = 0
    commit = core._read('maintenance', identity, 'commit-intent')
    for entry in commit['files']:
        source_item = plan['files'][index]; path = Path(source_item['path'])
        checkpoint = _existing_checkpoint(core, plan, index)
        index += 2
        if not path.exists() and checkpoint:
            tombstone = Path(checkpoint['tombstone'])
            if tombstone.exists():
                path = tombstone
            else:
                entries.append({**entry, 'operation_id': identity, 'purged': True}); continue
        entries.append({**entry, 'retained_path': str(path), 'operation_id': identity})
    return entries
