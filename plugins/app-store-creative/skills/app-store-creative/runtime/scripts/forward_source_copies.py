"""Pinned forward-source directories and receipt-bound full-tree manifests."""
from pathlib import Path
import base64
import hashlib
import json

from artifact_lifecycle import canonical
from reverse_relocation import _identity, _tree


def identities(binding):
    return {key: _identity(Path(path)) for key, path in binding.items()}


def groups(plan):
    changed = {key: Path(path) for key, path in plan['from'].items() if path != plan['to'][key]}
    return {key: path for key, path in changed.items()
            if not any(path != other and path.is_relative_to(other) for other in changed.values())}


def capture(core, plan):
    copies = []
    for key, path in groups(plan).items():
        identity = plan['source_root_identities'][key]
        if _identity(path) != identity:
            raise ValueError('Forward source directory identity changed')
        if identity is None:
            continue
        files = _tree(path)
        if _identity(path) != identity:
            raise ValueError('Forward source directory identity changed while scanning')
        copies.append({'group': key, 'path': str(path), 'directory_identity': identity, 'files': files})
    return copies


def verify_capture(core, plan, intent):
    from relocation_inventory import _manifest, _hash
    copies = intent.get('source_copies')
    receipt = intent.get('receipt', {})
    prepared = core._read('relocations', plan['id'], 'prepared')
    if (not isinstance(copies, list) or intent.get('plan_sha256') != _hash(plan)
            or intent.get('prepared_sha256') != _hash(prepared)
            or receipt.get('source_copies_sha256') != _hash(copies)
            or receipt.get('id') != plan['id'] or receipt.get('status') != 'SWITCHED'
            or receipt.get('from') != plan['from'] or receipt.get('to') != plan['to']
            or receipt.get('project_id') != core.config.get('project', {}).get('id')
            or receipt.get('config_path') != str(core.config_path)):
        raise ValueError('Forward source copy evidence differs')
    source = base64.b64decode(intent['source_config_base64'], validate=True)
    if not isinstance(plan.get('configuration_change'), dict):
        raise ValueError('Forward source configuration layer authority is required')
    from configuration_layers import owning_document
    authority = owning_document(core.paths.project, core.config_path, plan['configuration_change'])
    if source != authority['source_bytes']:
        raise ValueError('Forward source owning backup differs')
    source_config = authority['source_effective_config']
    if (hashlib.sha256(source).hexdigest() != plan['source_config_file_sha256']
            or _hash(source_config) != plan['source_config_sha256']
            or _hash(intent['target_config']) != plan['target_config_sha256']):
        raise ValueError('Forward source configuration evidence differs')
    roots = groups(plan)
    expected = {key for key in roots if plan['source_root_identities'][key] is not None}
    if (any(not isinstance(copy, dict) for copy in copies)
            or len(copies) != len(expected) or {copy['group'] for copy in copies} != expected):
        raise ValueError('Forward source copy groups differ')
    verified = []
    for copy in copies:
        key = copy['group']; directory_identity = plan['source_root_identities'][key]
        if (copy.get('path') != str(roots[key]) or copy.get('directory_identity') != directory_identity
                or not isinstance(directory_identity, list) or len(directory_identity) != 2
                or any(type(value) is not int or value < 0 for value in directory_identity)):
            raise ValueError('Forward source copy directory scope differs')
        verified.append((copy, _manifest(copy['files'])))
    return verified


def verify(core, plan):
    from relocation_inventory import _hash
    identity = plan['id']
    intent = core._read('relocations', identity, 'switch-intent')
    receipt = core._read('relocations', identity, 'switched')
    if canonical(receipt) != canonical(intent.get('receipt')) or plan.get('config_path') != str(core.config_path):
        raise ValueError('Forward source copy evidence differs')
    core._verified_relocation_controls(plan, intent)
    captures = verify_capture(core, plan, intent)
    from configuration_installation import _expected
    installation = core._read('relocations', identity, 'configuration-installation')
    expected_installation, _ = _expected(core, identity)
    if any(installation.get(key) != value for key, value in expected_installation.items()):
        raise ValueError('Forward source installation evidence differs')
    verified = []
    for copy, manifest in captures:
        key = copy['group']; directory_identity = copy['directory_identity']
        controls = {}
        root = Path(copy['path'])
        # These immutable controls are added after the pre-switch capture.
        names = ['switch-intent', 'switch-outcome', 'resume-intent', 'switched', 'configuration-installation']
        candidates = [(core._path('relocations', identity, suffix), 'relocations', identity, suffix) for suffix in names]
        source_key = _hash(plan['from'])
        candidates.append((core._path('storage-fences', source_key, identity), 'storage-fences', source_key, identity))
        for current, category, record_id, suffix in candidates:
            source_path = Path(plan['from']['workspace']) / current.relative_to(core.paths.workspace)
            if source_path.is_relative_to(root) and (current.exists() or current.is_symlink()):
                record = core._read(category, record_id, suffix)
                encoded = canonical(record)
                controls[source_path.relative_to(root).as_posix()] = {
                    'size_bytes': len(encoded), 'sha256': hashlib.sha256(encoded).hexdigest()}
        verified.append(({'group': key, 'staging': str(root), 'destination_identity': directory_identity,
                          'kind': 'forward-source', 'control_files': controls}, manifest))
    return verified
