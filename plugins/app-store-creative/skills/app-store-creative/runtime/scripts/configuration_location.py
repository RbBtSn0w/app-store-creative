"""Explicit, byte-bound transfer of a host-local configuration authority."""
import hashlib
from pathlib import Path
from configuration_layers import _read_regular, local_path_for, load


def key(path):
    return hashlib.sha256(str(path).encode()).hexdigest()


def authority_matches(core, source_path, source_project=None):
    """Resolve only immutable, explicit transfers; copied configurations fail closed."""
    if not isinstance(source_path,str) or not Path(source_path).is_absolute():
        return False
    path = source_path
    seen = set()
    while path != str(core.config_path):
        if path in seen:
            raise ValueError('Configuration location authority cycle')
        seen.add(path)
        try:
            receipt = core._read('configuration-locations', key(path))
        except FileNotFoundError:
            return False
        if (receipt.get('status') != 'ACTIVATED' or receipt.get('source_path') != path
                or receipt.get('project_id') != core.config.get('project', {}).get('id')
                or not isinstance(receipt.get('actor'),str) or not receipt['actor'].strip()
                or not isinstance(receipt.get('reason'),str) or not receipt['reason'].strip()):
            raise ValueError('Invalid configuration location authority')
        if source_project is not None and receipt['source_project'] != source_project:
            return False
        path = receipt['target_path']
        source_project = receipt['target_project']
    if not seen:
        return source_project is None or source_project == str(core.paths.project)
    layers = load(core.paths.project, core.config_path)
    project_sha, local_sha = storage_successor_hashes(core, receipt)
    if (layers.project_sha256 != project_sha
            or layers.local_sha256 != local_sha
            or str(core.paths.project) != receipt['target_project']):
        raise ValueError('Migrated configuration differs from committed authority')
    return True


def storage_successor_hashes(core, receipt):
    """Advance byte authority only through committed, exact storage switch evidence."""
    from artifact_lifecycle import canonical
    binding = receipt['binding']
    project_sha, local_sha = receipt['project_sha256'], receipt['local_sha256']
    seen = set()
    while binding != core.paths.binding():
        identity = hashlib.sha256(canonical(binding)).hexdigest()
        if identity in seen:
            raise ValueError('Configuration storage authority cycle')
        seen.add(identity)
        edge = core._read('storage-bindings', identity)
        switched = core._read('relocations', edge['relocation_id'], 'switched')
        plan = core._read('relocations', edge['relocation_id'])
        change = plan.get('configuration_change') or {}
        if (edge.get('from') != binding or switched.get('from') != binding
                or switched.get('status') != 'SWITCHED'
                or switched.get('to') != edge.get('to') or plan.get('to') != edge.get('to')
                or switched.get('config_path') != receipt['target_path']
                or switched.get('project_id') != receipt['project_id']
                or hashlib.sha256(canonical(switched)).hexdigest() != edge.get('switch_sha256')
                or change.get('source_project_sha256') != project_sha
                or change.get('source_local_sha256') != local_sha
                or change.get('source_binding') != binding
                or change.get('target_binding') != edge.get('to')):
            raise ValueError('Configuration storage authority differs')
        if change.get('target_path') == receipt['target_path']:
            project_sha = change['target_sha256']
        elif change.get('target_path') == str(local_path_for(Path(receipt['target_path']))):
            local_sha = change['target_sha256']
        else:
            raise ValueError('Configuration storage target authority differs')
        binding = edge['to']
    return project_sha, local_sha


def relocate_configuration(core, destination, actor, reason):
    """Commit authority only after exact destination bytes are durably published."""
    if any(not isinstance(v,str) or not v.strip() for v in (actor,reason)):
        raise ValueError('Configuration relocation requires actor and reason')
    destination = Path(destination)
    if not destination.is_absolute() or destination.resolve() != destination:
        raise ValueError('Configuration destination must be absolute without aliases')
    target = destination / core.config_path.name
    source = str(core.config_path)
    if target == core.config_path:
        raise ValueError('Configuration destination must differ from the current configuration')
    record_path = core._path('configuration-locations',key(source))
    if record_path.exists():
        receipt = core._read('configuration-locations',key(source))
        if receipt.get('target_path') != str(target):
            raise ValueError('Configuration already relocated elsewhere')
        from artifact_lifecycle import Lifecycle
        moved = Lifecycle.from_configuration(destination,target)
        if not authority_matches(moved,source,str(core.paths.project)):
            raise ValueError('Configuration relocation authority differs')
        return receipt
    with core.transaction():
        layers = core._configuration_layers
        # Absolute roots ensure changing the project directory cannot reinterpret data.
        destination.mkdir(parents=True,exist_ok=True)
        from safe_staging import staged_file
        files = [(target,layers.project_bytes)]
        if layers.local_bytes is not None:
            files.append((local_path_for(target),layers.local_bytes))
        for path,payload in files:
            if path.exists() or path.is_symlink():
                if path == local_path_for(target) and path.lstat().st_mode & 0o077:
                    raise ValueError('Private configuration destination must be owner-only')
                if _read_regular(path) != payload:
                    raise ValueError('Configuration destination contains different bytes')
                continue
            with staged_file(path.parent) as staged:
                staged.stream.write(payload); staged.sync(); staged.publish(path)
            path.chmod(0o600 if path == local_path_for(target) else core.config_path.stat().st_mode & 0o777)
        def verify_target():
            moved_layers = load(destination,target)
            if (moved_layers.project_sha256 != layers.project_sha256
                    or moved_layers.local_sha256 != layers.local_sha256):
                raise ValueError('Configuration bytes changed before authority commit')
            if moved_layers.paths.binding() != core.paths.binding():
                raise ValueError('Configuration relocation changes storage roots')
        verify_target()
        receipt = {'schema_version':1,'id':key(source),'status':'ACTIVATED',
            'source_path':source,'target_path':str(target),
            'source_project':str(core.paths.project),'target_project':str(destination),
            'project_id':core.config['project']['id'],'binding':core.paths.binding(),
            'project_sha256':layers.project_sha256,'local_sha256':layers.local_sha256,
            'actor':actor,'reason':reason}
        receipt = core._record('configuration-locations',receipt,precommit=verify_target)
        return receipt


def check_source_write_fence(core):
    """A completed transfer retires the original configuration for writes."""
    record_path = core._path('configuration-locations', key(core.config_path))
    if record_path.exists() or record_path.is_symlink():
        core._read('configuration-locations', key(core.config_path))
        raise ValueError('Configuration authority relocated; use its activated destination')
