"""Verify planned copied object bytes independently of target activation."""
import hashlib
from pathlib import Path
from artifact_lifecycle import Lifecycle, canonical, digest
from delivery_lifecycle import relative_name
from operation_history import read_lock


def inspect(core, identity):
    result = {'id': identity, 'status': 'UNKNOWN', 'object_integrity_verified': False,
              'checked_files': 0, 'errors': [], 'remote_write': False,
              'scope': 'Exact object files copied by this relocation; not all current media or historical execution'}
    status = core.relocation_status(identity)
    if status['status'] != 'SWITCHED':
        return {**result, 'status': 'INCOMPLETE'}
    if status['target_activation_status'] != 'VERIFIED':
        return {**result, 'status': 'FAIL', 'errors': status['target_activation_errors']}
    try:
        plan = core._read('relocations', identity)
        intent = core._read('relocations', identity, 'switch-intent')
        if intent.get('plan_sha256') != hashlib.sha256(canonical(plan)).hexdigest():
            raise ValueError('Relocation plan intent binding differs')
        target = Lifecycle(core.paths.project, intent['target_config'], core.config_path)
        target._assert_paths()
        lock = target.paths.workspace / 'write.lock'
        if not lock.exists() and not lock.is_symlink():
            return {**result, 'errors': ['Target read lock is not established; inspection will not create it']}
        with read_lock(target):
            target._check_storage_activation()
            if target._read('relocations', identity) != plan:
                raise ValueError('Target relocation plan differs')
            for item in plan['files']:
                if item['root'] != 'objects':
                    continue
                path = Path(plan['to']['objects']) / relative_name(item['path'])
                if path.resolve() != path or not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                    raise ValueError('Relocated object bytes differ: ' + item['path'])
                result['checked_files'] += 1
        if result['checked_files']:
            result['status'] = 'PASS'; result['object_integrity_verified'] = True
    except (ValueError, OSError, KeyError, TypeError) as error:
        result['status'] = 'FAIL'; result['errors'].append(str(error))
    return result
