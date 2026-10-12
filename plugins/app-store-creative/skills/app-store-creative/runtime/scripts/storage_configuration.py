"""Read-only draft storage resolution shared by CLI, Studio and agents."""
import json
from pathlib import Path
import stat
from artifact_lifecycle import StoragePaths, STORAGE_DEFAULTS
from studio_contract import check_config


def preview(root, config, current=None, config_path=None):
    check_config(config)
    paths = StoragePaths.resolve(root, config)
    raw = config.get('storage', {})
    names = dict(zip(STORAGE_DEFAULTS, ('workspace', 'objects', 'releases', 'publications')))
    roots = {}
    for key, label in names.items():
        configured = raw.get(key)
        source = 'project' if key in raw else ('derived' if key == 'objectRoot' else 'default')
        roots[key] = {'configured': configured, 'source': source,
                      'resolved': str(getattr(paths, label))}
    current_paths = StoragePaths.resolve(root, current) if current is not None else None
    managed = False
    if current_paths is not None:
        owner = current_paths.workspace / 'owner.json'
        try:
            entry = owner.lstat()
        except FileNotFoundError:
            entry = None
        if entry is not None:
            if not stat.S_ISREG(entry.st_mode) or owner.resolve() != owner:
                raise ValueError('Managed storage owner is unsafe')
            expected = {'project': str(current_paths.project), 'project_id': current.get('project', {}).get('id')}
            if json.loads(owner.read_text()) != expected:
                raise ValueError('Workspace is owned by another project')
            managed = True
    changed = current_paths is not None and current_paths.binding() != paths.binding()
    return {'binding': paths.binding(), 'roots': roots, 'roots_changed': changed,
            'requires_relocation': managed and changed,
            'project_identity_conflict': managed and current.get('project', {}).get('id') != config.get('project', {}).get('id'),
            'configuration_path': str(Path(config_path).resolve()) if config_path is not None else None,
            'writes_performed': False}


def preview_configuration(root, config, config_path):
    """Resolve a shared draft against currently protected host-local authority."""
    from configuration_layers import load, compose
    layers = load(root, config_path)
    effective, _, sources = compose(root, config, layers.local_config)
    report = preview(root, effective, layers.config, layers.project_path)
    for key, source in sources.items():
        report['roots'][key]['source'] = source
    return report
