"""Read-only maintenance effect verification; recorded status is not sufficient."""
import hashlib
from artifact_lifecycle import canonical, digest
from operation_history import read_lock


def record_digest(record):
    return hashlib.sha256(canonical(record)).hexdigest()


def purge_checkpoint(core, plan, index, required=False):
    identity = plan['quarantine_id']; suffix = f'purge-file-{index}'
    path = core._path('maintenance', identity, suffix)
    if not path.exists() and not path.is_symlink():
        if required:
            raise ValueError('Missing purge file checkpoint')
        return None
    entry = core._read('maintenance', identity, suffix)
    item = plan['objects'][index]
    expected_path = str(core._quarantine_path(identity, item['sha256']))
    observed = entry.get('file_identity')
    if (entry.get('plan_id') != plan['id'] or entry.get('plan_sha256') != record_digest(plan)
            or entry.get('object') != item or entry.get('path') != expected_path
            or not isinstance(observed, list) or len(observed) != 2
            or any(type(value) is not int or value < 0 for value in observed)):
        raise ValueError('Purge file checkpoint binding differs')
    return entry


def completed_purge(core, plan):
    identity = plan['quarantine_id']
    result = core._read('maintenance', identity, 'purged')
    intent = core._read('maintenance', identity, 'purge-intent')
    operation = core._read('maintenance', identity)
    if (result.get('status') != 'purged' or result.get('plan_id') != plan['id']
            or result.get('purge_intent_sha256') != record_digest(intent)
            or intent.get('plan_id') != plan['id'] or intent.get('plan_sha256') != record_digest(plan)
            or intent.get('operation_sha256') != record_digest(operation)
            or result.get('bytes_removed') != sum(item['size_bytes'] for item in plan['objects'])):
        raise ValueError('Completed purge receipt binding differs')
    for index, item in enumerate(plan['objects']):
        purge_checkpoint(core, plan, index, required=True)
        path = core._quarantine_path(identity, item['sha256'])
        if path.exists() or path.is_symlink():
            raise ValueError('Purged object reappeared; preserve and investigate')
    return result


def inspect(core, identity):
    core._assert_paths(); core._live_configuration()
    result = {'id': identity, 'status': 'UNKNOWN', 'phase': 'UNKNOWN',
              'execution_verified': False, 'errors': [], 'remote_write': False}
    with read_lock(core):
        core._live_configuration()
        operation = core._read('maintenance', identity)
        kind = operation.get('operation'); result['operation'] = kind
        try:
            if kind == 'relocation-quarantine':
                from quarantine_inventory import _inspect
                row, _ = _inspect(core, operation)
                result['phase'] = row['phase']; result['observation'] = row
                if row['phase'] in ('PREPARED', 'QUARANTINED', 'RESTORED', 'CANCELLED', 'PURGED'):
                    result['status'] = 'PASS' if row['status'] in ('VERIFIED', 'PURGED') else 'FAIL'
                else:
                    result['status'] = 'INCOMPLETE'
            elif kind == 'quarantine':
                plan = core._read('maintenance', operation['plan_id'])
                if plan.get('operation') != 'cleanup-plan' or plan.get('storage') != core.paths.binding() or plan.get('objects') != operation.get('objects'):
                    raise ValueError('Quarantine plan or storage binding differs')
                purged = core._path('maintenance', identity, 'purged')
                restored = core._path('maintenance', identity, 'restored')
                if purged.exists() or purged.is_symlink():
                    result['phase'] = 'purged'
                    receipt = core._read('maintenance', identity, 'purged')
                    completed_purge(core, core._read('maintenance', receipt['plan_id']))
                elif restored.exists() or restored.is_symlink():
                    intent = restoration_intent(core, operation, plan)
                    receipt = core._read('maintenance', identity, 'restored')
                    if receipt.get('restore_intent_sha256') != record_digest(intent):
                        raise ValueError('Restoration receipt binding differs')
                    result['phase'] = 'restored'
                    if core._read('maintenance', identity, 'restored').get('status') != 'restored':
                        raise ValueError('Invalid restoration receipt')
                    for item in operation['objects']:
                        path = core.object_path(item['sha256'])
                        if not path.is_file() or path.is_symlink() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                            raise ValueError('Restored object integrity differs')
                        retained = core._quarantine_path(identity, item['sha256'])
                        if not retained.is_file() or retained.is_symlink() or retained.stat().st_size != item['size_bytes'] or digest(retained) != item['sha256']:
                            raise ValueError('Restoration retained copy integrity differs')
                elif core._path('maintenance', identity, 'restore-intent').exists() or core._path('maintenance', identity, 'restore-intent').is_symlink():
                    result['phase'] = 'RESTORING'
                    restoration_intent(core, operation, plan)
                    for item in operation['objects']:
                        active = core.object_path(item['sha256'])
                        retained = core._quarantine_path(identity, item['sha256'])
                        available = False
                        for path in (active, retained):
                            if path.exists() or path.is_symlink():
                                if not path.is_file() or path.is_symlink() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                                    raise ValueError('Restoration object integrity differs')
                                available = True
                        if not available:
                            raise ValueError('Restoration object is missing')
                    result['status'] = 'INCOMPLETE'
                    return result
                else:
                    result['phase'] = 'quarantined'
                    outcome = core._path('maintenance', identity, 'outcome')
                    if core._path('maintenance', identity, 'purge-intent').exists() or not outcome.exists():
                        result['status'] = 'INCOMPLETE'; return result
                    if core._read('maintenance', identity, 'outcome').get('status') != 'quarantined':
                        raise ValueError('Invalid quarantine outcome')
                    for item in operation['objects']:
                        path = core._quarantine_path(identity, item['sha256'])
                        if not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                            raise ValueError('Quarantine object integrity differs')
                        active = core.object_path(item['sha256'])
                        if active.exists() or active.is_symlink():
                            raise ValueError('Quarantined active object reappeared')
                result['status'] = 'PASS'
            elif kind in ('cleanup-plan', 'purge-plan', 'relocation-retention-plan', 'relocation-purge-plan'):
                result['phase'] = 'PLANNED'; result['status'] = 'NOT_EXECUTED'
            else:
                result['errors'].append('Unsupported maintenance execution scope')
        except (ValueError, OSError, KeyError, TypeError) as error:
            result['status'] = 'FAIL'; result['errors'].append(str(error))
    result['execution_verified'] = result['status'] == 'PASS'
    return result


def restoration_intent(core, operation, plan):
    intent = core._read('maintenance', operation['id'], 'restore-intent')
    if (intent.get('status') != 'restoring' or intent.get('operation_sha256') != record_digest(operation)
            or intent.get('plan_sha256') != record_digest(plan) or intent.get('storage') != core.paths.binding()):
        raise ValueError('Restoration intent binding differs')
    return intent
