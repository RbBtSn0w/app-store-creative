"""Named filesystem media backend with immutable content-addressed versions."""
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import tempfile
from operation_history import sync_directory


class FileSystemMediaStore:
    def __init__(self, name, root):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name):
            raise ValueError('External backend requires a safe configuration name')
        self.name = name
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.resolve() != self.root:
            raise ValueError('External backend requires an explicit absolute path without aliases')

    def object_path(self, reference):
        fields = {'schema_version', 'provider', 'backend', 'object_id', 'version', 'sha256', 'size_bytes'}
        if (not isinstance(reference, dict) or set(reference) != fields
                or type(reference.get('schema_version')) is not int or reference['schema_version'] != 1
                or reference.get('provider') != 'filesystem' or reference.get('backend') != self.name):
            raise ValueError('External object reference differs from configured backend')
        sha = reference['sha256']
        if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha)
                or reference['object_id'] != 'sha256:' + sha or reference['version'] != sha
                or type(reference['size_bytes']) is not int or reference['size_bytes'] < 0):
            raise ValueError('Invalid immutable external object reference')
        path = self.root / self.name / 'objects/sha256' / sha[:2] / sha
        if path.resolve() != path:
            raise ValueError('External object path contains aliases')
        return path

    def _verify(self, reference):
        path = self.object_path(reference)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError as error:
            raise ValueError('External object version is missing') from error
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('External object must be a regular file')
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        if sha != reference['sha256'] or info.st_size != reference['size_bytes']:
            raise ValueError('External object integrity differs from reference')
        return path

    @staticmethod
    def _copy(source, destination, sha, size):
        destination = Path(destination)
        if not destination.is_absolute() or destination.resolve() != destination:
            raise ValueError('External retrieval destination contains aliases')
        if destination.exists() or destination.is_symlink():
            raise ValueError('External retrieval destination already exists')
        created = []
        parent = destination.parent
        while not parent.exists():
            created.append(parent); parent = parent.parent
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.parent.resolve() != destination.parent:
            raise ValueError('External retrieval destination parent changed')
        parent_descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        staged_name = None
        staged_identity = None
        try:
            parent_info = os.fstat(parent_descriptor)
            current = destination.parent.lstat()
            if (destination.parent.resolve() != destination.parent
                    or (current.st_dev, current.st_ino) != (parent_info.st_dev, parent_info.st_ino)):
                raise ValueError('External retrieval destination parent changed')
            staged_name = '.creative-object-' + secrets.token_hex(16)
            descriptor = os.open(staged_name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent_descriptor)
            staged_info = os.fstat(descriptor)
            staged_identity = (staged_info.st_dev, staged_info.st_ino)
            with os.fdopen(descriptor, 'wb') as output:
                source_descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(source_descriptor, 'rb') as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise ValueError('External media source must be a regular file')
                    shutil.copyfileobj(stream, output)
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError('External media source changed during copy')
                output.flush(); os.fsync(output.fileno())
            copied_descriptor = os.open(staged_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                        dir_fd=parent_descriptor)
            with os.fdopen(copied_descriptor, 'rb') as stream:
                copied_info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(copied_info.st_mode)
                        or (copied_info.st_dev, copied_info.st_ino) != staged_identity):
                    raise ValueError('External staged object identity changed')
                copied_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            if copied_sha != sha or copied_info.st_size != size:
                raise ValueError('External copied object integrity differs')
            current = destination.parent.lstat()
            if (destination.parent.resolve() != destination.parent
                    or (current.st_dev, current.st_ino) != (parent_info.st_dev, parent_info.st_ino)):
                raise ValueError('External retrieval destination parent changed')
            os.link(staged_name, destination.name, src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor, follow_symlinks=False)
            os.fsync(parent_descriptor)
            for directory in created:
                sync_directory(directory.parent)
        finally:
            try:
                if staged_name is not None:
                    try:
                        current = os.stat(staged_name, dir_fd=parent_descriptor, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        if (current.st_dev, current.st_ino) == staged_identity:
                            os.unlink(staged_name, dir_fd=parent_descriptor)
            finally:
                os.close(parent_descriptor)

    def persist(self, source):
        source = Path(source)
        if source.resolve() != source or not source.is_file():
            raise ValueError('External media source must be an unaliased regular file')
        with source.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        reference = {'schema_version': 1, 'provider': 'filesystem', 'backend': self.name,
                     'object_id': 'sha256:' + sha, 'version': sha, 'sha256': sha,
                     'size_bytes': source.stat().st_size}
        path = self.object_path(reference)
        if path.exists():
            self._verify(reference)
        else:
            try:
                self._copy(source, path, sha, reference['size_bytes'])
            except FileExistsError:
                self._verify(reference)
        # Return a reference only after independently reading and checking its bytes.
        with tempfile.TemporaryDirectory(prefix='creative-external-readback-') as directory:
            self.retrieve(reference, Path(directory).resolve() / 'object')
        return reference

    def retrieve(self, reference, destination):
        source = self._verify(reference)
        self._copy(source, Path(destination), reference['sha256'], reference['size_bytes'])
        return {'retrieved': True, 'sha256': reference['sha256'], 'size_bytes': reference['size_bytes']}


def persist_managed(core, artifact_id, backend, root):
    from artifact_lifecycle import identifier
    with core.transaction():
        artifact = core.verify_artifact(artifact_id)
        store = managed_store(core, backend, root)
        reference = store.persist(core.object_path(artifact['sha256']))
        if reference['sha256'] != artifact['sha256'] or reference['size_bytes'] != artifact['size_bytes']:
            raise ValueError('External persistence differs from managed artifact')
        return core._record('external-media', {'id': identifier(), 'artifact_id': artifact_id,
            'run_id': artifact['run_id'], 'reference': reference, 'retrieval_verified': True})


def restore_managed(core, reference_id, backend, root):
    from artifact_lifecycle import identifier
    with core.transaction():
        saved = core._read('external-media', reference_id)
        artifact = core._read('artifacts', saved['artifact_id'])
        reference = saved['reference']
        store = managed_store(core, backend, root)
        store.object_path(reference)
        if reference['sha256'] != artifact['sha256'] or reference['size_bytes'] != artifact['size_bytes']:
            raise ValueError('External reference differs from managed artifact')
        store._verify(reference)
        destination = core.object_path(artifact['sha256'])
        restored = not destination.exists()
        if restored:
            store.retrieve(reference, destination)
        core.verify_artifact(artifact['id'])
        return core._record('external-retrievals', {'id': identifier(), 'artifact_id': artifact['id'],
            'run_id': artifact['run_id'], 'reference_id': reference_id, 'restored': restored,
            'sha256': artifact['sha256'], 'size_bytes': artifact['size_bytes']})


def managed_store(core, backend, root):
    root = resolve_backend_root(core, backend, root)
    store = FileSystemMediaStore(backend, root)
    for managed in (core.paths.workspace, core.paths.objects, core.paths.releases, core.paths.publications):
        if store.root == managed or store.root.is_relative_to(managed) or managed.is_relative_to(store.root):
            raise ValueError('External backend root overlaps managed storage')
    return store


def resolve_backend_root(core, backend, root=None):
    """Resolve protected host-local access without exporting machine paths."""
    if root is not None:
        return Path(root)
    layers = getattr(core, '_configuration_layers', None)
    local = layers.local_config if layers is not None else None
    configured = local.get('mediaBackends', {}).get(backend) if local else None
    if configured is None:
        raise ValueError('Named external backend has no host-local access configuration')
    if configured['provider'] != 'filesystem':
        raise ValueError('Unsupported external backend provider')
    return Path(configured['root'])
