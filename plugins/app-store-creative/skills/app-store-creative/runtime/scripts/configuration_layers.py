"""Project recipes and protected host-local storage use one precedence contract.

Runtime adoption must bind both documents before using this resolver for writes.
"""
from dataclasses import dataclass
import hashlib
import base64
import json
import os
from pathlib import Path
import stat
import subprocess
from artifact_lifecycle import StoragePaths, STORAGE_DEFAULTS, canonical
from storage_git_policy import repository_for, git_environment


def local_path_for(project_path):
    path = Path(project_path)
    return path.with_name(path.stem + '.local' + path.suffix)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate configuration key: ' + key)
        value[key] = item
    return value


def _document(raw):
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError('Configuration document must be an object')
    return value


def _read_regular(path, optional=False):
    try:
        before = path.lstat()
    except FileNotFoundError:
        if optional:
            return None
        raise
    if not stat.S_ISREG(before.st_mode) or path.resolve() != path:
        raise ValueError('Configuration must be a regular file without symlinks')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Configuration identity changed while reading')
        raw = stream.read(30 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(opened, field) != getattr(after, field) for field in fields):
        raise ValueError('Configuration changed while reading')
    if len(raw) > 30 * 1024 * 1024:
        raise ValueError('Configuration exceeds 30 MB')
    return raw


def verify_local_git_protection(path):
    repository = repository_for(path)
    if repository is None:
        return
    relative = path.relative_to(repository).as_posix()
    command = ['git', '--literal-pathspecs', '-C', str(repository)]
    tracked = subprocess.run([*command, 'ls-files', '-z', '--', relative], capture_output=True, env=git_environment())
    if tracked.returncode:
        raise ValueError('Local configuration Git index could not be verified')
    if tracked.stdout:
        raise ValueError('Host-local configuration is tracked by Git; it must remain untracked')
    ignored = subprocess.run(['git', '-C', str(repository), 'check-ignore', '--quiet', '--no-index', '--', relative], capture_output=True, env=git_environment())
    if ignored.returncode == 1:
        raise ValueError('Host-local configuration must be ignored by actual Git rules')
    if ignored.returncode:
        raise ValueError('Local configuration Git ignore protection could not be verified')


def compose(root, project, local=None):
    from project_identity import require_project_identity
    require_project_identity(project)
    from archive_policy import resolve as resolve_archive_policy
    resolve_archive_policy(project)
    if not isinstance(project, dict):
        raise ValueError('Project configuration must be an object')
    shared = project.get('storage', {})
    if not isinstance(shared, dict):
        raise ValueError('Project storage must be an object')
    overrides = {}
    if local is not None:
        if (not isinstance(local, dict) or not {'schema_version', 'project_id', 'storage'}.issubset(local)
                or set(local) - {'schema_version', 'project_id', 'storage', 'mediaBackends'}
                or type(local['schema_version']) is not int or local['schema_version'] != 1):
            raise ValueError('Invalid host-local configuration schema')
        identity = project.get('project', {})
        if not isinstance(identity, dict):
            raise ValueError('Project identity must be an object')
        project_id = identity.get('id')
        if not isinstance(project_id, str) or not project_id or local['project_id'] != project_id:
            raise ValueError('Host-local configuration belongs to another project')
        backends = local.get('mediaBackends', {})
        if not isinstance(backends, dict):
            raise ValueError('Host-local mediaBackends must be an object')
        import re
        for name, backend in backends.items():
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name)
                    or not isinstance(backend, dict) or set(backend) != {'provider', 'root'}
                    or backend['provider'] != 'filesystem' or not isinstance(backend['root'], str)
                    or not Path(backend['root']).is_absolute()):
                raise ValueError('Invalid named host-local media backend')
        overrides = local['storage']
        if not isinstance(overrides, dict) or set(overrides) - set(STORAGE_DEFAULTS):
            raise ValueError('Host-local configuration may only override storage roots')
    config = json.loads(canonical(project))
    if overrides:
        config['storage'] = {**shared, **overrides}
    paths = StoragePaths.resolve(root, config)
    sources = {key: ('local' if key in overrides else 'project' if key in shared else
                     'derived' if key == 'objectRoot' else 'default') for key in STORAGE_DEFAULTS}
    return config, paths, sources


def _identity(path):
    try:
        entry = path.lstat()
    except FileNotFoundError:
        return None
    return {'device':entry.st_dev, 'inode':entry.st_ino, 'mode':entry.st_mode,
            'size_bytes':entry.st_size, 'mtime_ns':entry.st_mtime_ns, 'ctime_ns':entry.st_ctime_ns}


@dataclass(frozen=True)
class ConfigurationLayers:
    project_path: Path
    local_path: Path
    project_config: dict
    local_config: dict | None
    config: dict
    paths: StoragePaths
    sources: dict
    project_sha256: str
    local_sha256: str | None
    revision: str
    project_bytes: bytes
    local_bytes: bytes | None
    project_identity: dict
    local_identity: dict | None


def load(root, config_path):
    root = Path(root).resolve()
    project_path = Path(config_path)
    if not project_path.is_absolute():
        project_path = root / project_path
    local_path = local_path_for(project_path)
    project_identity = _identity(project_path); local_identity = _identity(local_path)
    project_bytes = _read_regular(project_path)
    local_bytes = _read_regular(local_path, optional=True)
    if local_bytes is not None:
        verify_local_git_protection(local_path)
    project = _document(project_bytes)
    local = _document(local_bytes) if local_bytes is not None else None
    config, paths, sources = compose(root, project, local)
    # Bind observed absence as well as both documents; callers must revalidate before mutations.
    if (_read_regular(project_path) != project_bytes or
            _read_regular(local_path, optional=True) != local_bytes):
        raise ValueError('Configuration layers changed while resolving')
    if local_bytes is not None:
        verify_local_git_protection(local_path)
    if _identity(project_path) != project_identity or _identity(local_path) != local_identity:
        raise ValueError('Configuration file identities changed while resolving')
    project_sha = hashlib.sha256(project_bytes).hexdigest()
    local_sha = hashlib.sha256(local_bytes).hexdigest() if local_bytes is not None else None
    revision = project_sha if local_sha is None else hashlib.sha256(canonical({'project':project_sha, 'local':local_sha})).hexdigest()
    return ConfigurationLayers(project_path, local_path, project, local, config, paths, sources,
                               project_sha, local_sha, revision, project_bytes, local_bytes,
                               project_identity, local_identity)


def plan_storage_change(layers, storage):
    """Describe one owning-layer update; no configuration or media is written."""
    from artifact_lifecycle import configuration_identity
    requested = json.loads(canonical(storage))
    target_project = json.loads(canonical(layers.project_config))
    target_project['storage'] = requested
    desired = StoragePaths.resolve(layers.paths.project, target_project)
    if layers.local_config is None:
        target_path = layers.project_path
        target_document = target_project
        effective = target_project
    else:
        # A complete local root set prevents omitted fields falling back to old shared roots.
        values = {key: requested.get(key, str(Path(requested.get('workspaceRoot', '.creative')) / 'objects')
                  if key == 'objectRoot' else default) for key, default in STORAGE_DEFAULTS.items()}
        target_document = {**json.loads(canonical(layers.local_config)), 'storage':values}
        target_path = layers.local_path
        effective, observed, _ = compose(layers.paths.project, layers.project_config, target_document)
        if observed.binding() != desired.binding():
            raise ValueError('Target configuration layers do not resolve the requested roots')
    recipe_sha = configuration_identity(layers.config)
    if configuration_identity(effective) != recipe_sha:
        raise ValueError('Storage change must preserve the production recipe')
    target_bytes = canonical(target_document)
    target_sha = hashlib.sha256(target_bytes).hexdigest()
    target_revision = target_sha if layers.local_config is None else hashlib.sha256(
        canonical({'project':layers.project_sha256, 'local':target_sha})).hexdigest()
    return {'schema_version':1, 'operation':'configuration-storage-change',
            'project_path':str(layers.project_path), 'local_path':str(layers.local_path),
            'source_revision':layers.revision, 'source_project_sha256':layers.project_sha256,
            'source_local_sha256':layers.local_sha256,
            'source_project_bytes_base64':base64.b64encode(layers.project_bytes).decode('ascii'),
            'source_local_bytes_base64':base64.b64encode(layers.local_bytes).decode('ascii') if layers.local_bytes is not None else None,
            'source_project_identity':layers.project_identity, 'source_local_identity':layers.local_identity,
            'source_recipe_sha256':recipe_sha, 'requested_storage':requested,
            'source_binding':layers.paths.binding(), 'target_binding':desired.binding(),
            'target_path':str(target_path), 'target_bytes_base64':base64.b64encode(target_bytes).decode('ascii'),
            'target_sha256':target_sha, 'target_revision':target_revision, 'writes_performed':False}


def verify_storage_change(root, config_path, plan):
    if not isinstance(plan, dict) or plan.get('operation') != 'configuration-storage-change':
        raise ValueError('Invalid configuration storage change plan')
    layers = load(root, config_path)
    actual = plan_storage_change(layers, plan.get('requested_storage'))
    if canonical(actual) != canonical(plan):
        raise ValueError('Configuration storage change plan is stale or differs')
    return actual


def observation(layers):
    """Private runtime provenance; local paths are not portable archive metadata."""
    return {'schema_version':1, 'revision':layers.revision,
            'project_document':{'path':str(layers.project_path), 'sha256':layers.project_sha256,
                                'identity':layers.project_identity},
            'local_document':{'path':str(layers.local_path), 'present':layers.local_bytes is not None,
                              'sha256':layers.local_sha256, 'identity':layers.local_identity},
            'sources':layers.sources}


def owning_document(root, config_path, plan):
    """Verify recorded layer consistency; live authority must be reobserved separately."""
    root = Path(root).resolve()
    project_path = Path(config_path).resolve()
    local_path = local_path_for(project_path)
    if plan.get('project_path') != str(project_path) or plan.get('local_path') != str(local_path):
        raise ValueError('Configuration owning paths differ from caller authority')
    project_bytes = base64.b64decode(plan['source_project_bytes_base64'], validate=True)
    encoded_local = plan['source_local_bytes_base64']
    local_bytes = base64.b64decode(encoded_local, validate=True) if encoded_local is not None else None
    project = _document(project_bytes); local = _document(local_bytes) if local_bytes is not None else None
    config, paths, sources = compose(root, project, local)
    project_sha = hashlib.sha256(project_bytes).hexdigest()
    local_sha = hashlib.sha256(local_bytes).hexdigest() if local_bytes is not None else None
    revision = project_sha if local_sha is None else hashlib.sha256(canonical({'project':project_sha,'local':local_sha})).hexdigest()
    layers = ConfigurationLayers(project_path, local_path, project, local, config, paths, sources,
                                 project_sha, local_sha, revision, project_bytes, local_bytes,
                                 plan['source_project_identity'], plan['source_local_identity'])
    if canonical(plan_storage_change(layers, plan.get('requested_storage'))) != canonical(plan):
        raise ValueError('Configuration owning document plan is inconsistent')
    target_bytes = base64.b64decode(plan['target_bytes_base64'], validate=True)
    target_document = _document(target_bytes)
    effective = target_document if local is None else compose(root, project, target_document)[0]
    identity = layers.project_identity if local is None else layers.local_identity
    if not isinstance(identity, dict) or not stat.S_ISREG(identity.get('mode', 0)):
        raise ValueError('Configuration owning document requires a regular source identity')
    return {'path':project_path if local is None else local_path,
            'source_bytes':project_bytes if local is None else local_bytes,
            'target_bytes':target_bytes, 'source_identity':identity,
            'mode':identity['mode'] & 0o777, 'source_effective_config':config, 'effective_config':effective}
