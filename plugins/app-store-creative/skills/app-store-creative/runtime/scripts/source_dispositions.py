"""Validated views of source-side quarantine files; immutable manifests stay unchanged."""
from pathlib import Path


def views(core):
    from quarantine_commit import _load, _check_locations, _matches
    records = core.paths.workspace / 'records/maintenance'
    if records.resolve() != records:
        raise ValueError('Source disposition records contain aliases')
    entries, errors, claimed = [], [], set()
    for path in sorted(records.glob('*.json')):
        try:
            operation = core._read('maintenance', path.stem)
            if operation.get('operation') != 'relocation-quarantine':
                continue
            purge = core._path('maintenance', operation['id'], 'purge-intent')
            if purge.exists() or purge.is_symlink():
                from purge_observations import source_entries
                entries.extend(source_entries(core, operation['id']))
                continue
            intent_path = core._path('maintenance', operation['id'], 'commit-intent')
            if not intent_path.exists() and not intent_path.is_symlink():
                continue
            if operation.get('storage') != core.paths.binding():
                from quarantine_inventory import _authority
                _, _, _, phase = _authority(core, operation, historical=True)
                if phase == 'RESTORED':
                    _check_locations(core._read('maintenance', operation['id'], 'commit-intent'))
                    continue
            operation, _ = _load(core, operation['id'])
            intent = core._read('maintenance', operation['id'], 'commit-intent')
            _check_locations(intent)
            if core._path('maintenance', operation['id'], 'restored').exists():
                continue
            local = []
            for entry in intent['files']:
                source, retained = Path(entry['source']['path']), Path(entry['retained_path'])
                if source.exists():
                    continue
                if not _matches(retained, entry['source']):
                    raise ValueError('Source disposition retained bytes differ')
                if str(source) in claimed:
                    raise ValueError('Source disposition claimed by multiple operations')
                local.append({**entry, 'operation_id': operation['id']})
            claimed.update(entry['source']['path'] for entry in local)
            entries.extend(local)
        except (ValueError, OSError, KeyError, TypeError) as error:
            errors.append({'id': path.stem, 'reason': str(error) or type(error).__name__})
    return entries, errors
