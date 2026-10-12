"""Relocation gates preserve ownership of unfinished maintenance operations."""
from relocation_quarantine import _hash


def check_relocation(core):
    records = core.paths.workspace / 'records/maintenance'
    if records.resolve() != records:
        raise ValueError('Maintenance fence records contain aliases')
    for path in sorted(records.glob('*.json')):
        operation = core._read('maintenance', path.stem)
        kind = operation.get('operation')
        if kind == 'quarantine':
            terminal = False
            for suffix, status in [('restored', 'restored'), ('purged', 'purged')]:
                marker = core._path('maintenance', operation['id'], suffix)
                if marker.exists() or marker.is_symlink():
                    if core._read('maintenance', operation['id'], suffix).get('status') != status:
                        raise ValueError('Maintenance terminal evidence differs')
                    terminal = True
            if not terminal:
                raise ValueError(f"Relocation blocked by unfinished maintenance {operation['id']}")
        elif kind == 'relocation-quarantine':
            from quarantine_inventory import _authority
            _, _, _, phase = _authority(core, operation, historical=True)
            if phase in ('CANCELLED', 'RESTORED'):
                continue
            marker = core._path('maintenance', operation['id'], 'purged')
            if marker.exists() or marker.is_symlink():
                if phase != 'QUARANTINED':
                    raise ValueError('Maintenance purge terminal phase differs')
                intent = core._read('maintenance', operation['id'], 'purge-intent')
                plan = core._read('maintenance', intent['plan_id'])
                done = core._read('maintenance', operation['id'], 'purged')
                if (plan.get('operation') != 'relocation-purge-plan' or plan.get('quarantine_id') != operation['id']
                        or plan.get('storage') != operation['storage'] or plan.get('operation_sha256') != _hash(operation)
                        or intent.get('plan_sha256') != _hash(plan) or done.get('status') != 'PURGED'
                        or done.get('plan_id') != plan['id'] or done.get('purge_intent_sha256') != _hash(intent)):
                    raise ValueError('Maintenance purge terminal evidence differs')
                continue
            raise ValueError(f"Relocation blocked by unfinished maintenance {operation['id']} ({phase})")
