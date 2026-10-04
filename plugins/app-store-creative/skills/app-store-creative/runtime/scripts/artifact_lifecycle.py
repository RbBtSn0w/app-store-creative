"""Canonical, local-first records and content storage for creative production."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from delivery_lifecycle import DeliveryOperations, relative_name, verify_archive, restore_archive
from publication_lifecycle import PublicationOperations
from retention_lifecycle import RetentionOperations
from incident_lifecycle import IncidentOperations
from lease_lifecycle import LeaseOperations, duration
from remote_observations import ObservationOperations
from input_lifecycle import InputOperations
from inventory_lifecycle import InventoryOperations, files_without_links
from relocation_lifecycle import RelocationOperations


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def configuration_identity(config):
    """Hash the reviewed recipe independently of host-local storage placement."""
    recipe = {key: value for key, value in config.items() if key != 'storage'}
    return hashlib.sha256(canonical(recipe)).hexdigest()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return uuid.uuid4().hex


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', value):
        raise ValueError('Invalid record identity')
    return value


def overlaps(a, b):
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


@dataclass(frozen=True)
class StoragePaths:
    project: Path
    workspace: Path
    objects: Path
    releases: Path
    publications: Path

    @classmethod
    def resolve(cls, root, config):
        root = Path(root).resolve()
        raw = config.get('storage', {})
        if not isinstance(raw, dict):
            raise ValueError('storage must be an object')
        defaults = {'workspaceRoot': '.creative', 'objectRoot': '.creative/objects',
                    'releaseRoot': 'creative-releases', 'publicationRoot': 'creative-publications'}
        unknown = set(raw) - set(defaults)
        if unknown:
            raise ValueError(f'Unknown storage fields: {sorted(unknown)}')
        paths = []
        for key, default in defaults.items():
            value = raw.get(key, str(Path(raw.get('workspaceRoot', '.creative')) / 'objects') if key == 'objectRoot' else default)
            if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError(f'Invalid storage path: {key}')
            path = Path(value)
            resolved = (path if path.is_absolute() else root / path).resolve()
            if not path.is_absolute() and not resolved.is_relative_to(root):
                raise ValueError('External storage requires an explicit absolute path, not a relative escape')
            if resolved == root:
                raise ValueError('Storage cannot be the project root')
            if resolved == Path(resolved.anchor) or overlaps(resolved, root / '.git'):
                raise ValueError('Storage cannot contain repository metadata or filesystem root')
            paths.append(resolved)
        workspace, objects, releases, publications = paths
        if workspace == objects or (overlaps(workspace, objects) and not objects.is_relative_to(workspace)):
            raise ValueError('Storage overlap: workspace cannot be inside object root')
        for a, b in ((releases, publications), (releases, workspace), (releases, objects),
                     (publications, workspace), (publications, objects)):
            if overlaps(a, b):
                raise ValueError('Storage roots overlap')
        return cls(root, workspace, objects, releases, publications)

    def binding(self):
        return {key: str(getattr(self, key)) for key in ('workspace', 'objects', 'releases', 'publications')}


class Lifecycle(DeliveryOperations, PublicationOperations, RetentionOperations, IncidentOperations, LeaseOperations, ObservationOperations, InputOperations, InventoryOperations, RelocationOperations):
    def __init__(self, root, config, config_path=None):
        self.paths = StoragePaths.resolve(root, config)
        self.config = json.loads(canonical(config))
        self.config_path = Path(config_path).resolve() if config_path is not None else self.paths.project / 'creative.config.json'
        self._explicit_config_path = config_path is not None
        self._owned_leases = {}

    def _assert_paths(self):
        for path in (self.paths.workspace, self.paths.objects, self.paths.releases, self.paths.publications):
            if path.resolve() != path:
                raise ValueError('Storage location changed through a symlink')

    @contextmanager
    def transaction(self):
        self._assert_paths()
        self._check_storage_write_fence()
        self._check_storage_activation()
        self._live_configuration()
        self.paths.workspace.mkdir(parents=True, exist_ok=True)
        owner = self.paths.workspace / 'owner.json'
        authority = self.paths.workspace / 'configuration-authority.json'
        lock = self.paths.workspace / 'write.lock'
        if lock.is_symlink() or owner.is_symlink() or authority.is_symlink():
            raise ValueError('Symlinked workspace metadata')
        with lock.open('a+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            self._check_storage_write_fence()
            self._check_storage_activation()
            self._live_configuration()
            identity = {'project': str(self.paths.project), 'project_id': self.config.get('project', {}).get('id')}
            if owner.exists():
                if json.loads(owner.read_text()) != identity:
                    raise ValueError('Workspace is owned by another project')
            else:
                self._write_path(owner, identity)
            configuration = {'config_path': str(self.config_path)}
            if authority.exists():
                if json.loads(authority.read_text()) != configuration:
                    raise ValueError('Workspace belongs to another configuration authority')
            else:
                self._write_path(authority, configuration)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _path(self, category, identity, suffix=None):
        path = self.paths.workspace / 'records' / category / safe_id(identity)
        if suffix:
            path = path / (safe_id(suffix) + '.json')
        else:
            path = path.with_suffix('.json')
        if not path.resolve().is_relative_to(self.paths.workspace):
            raise ValueError('Record path escapes workspace')
        return path

    def _read(self, category, identity, suffix=None):
        path = self._path(category, identity, suffix)
        if path.is_symlink():
            raise ValueError('Symlinked record')
        data = json.loads(path.read_text())
        if data.get('schema_version') != 1:
            raise ValueError('Unsupported record schema')
        return data

    def _write_path(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise ValueError('Immutable record already exists')
        fd, tmp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(canonical(data)); stream.flush(); os.fsync(stream.fileno())
            os.link(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _record(self, category, data, suffix=None):
        data = {'schema_version': 1, 'created_at': now(), **data}
        self._write_path(self._path(category, data['id'], suffix), data)
        return data

    def _run(self, identity):
        run = self._read('runs', identity)
        self.resolve_storage_binding(run['storage'])
        return run

    def start_run(self, target, source_hashes=None):
        with self.transaction():
            return self._record('runs', {'id': identifier(), 'config': self.config,
                                         'config_sha256': configuration_identity(self.config),
                                         'config_snapshot_sha256': hashlib.sha256(canonical(self.config)).hexdigest(),
                                         'target': target, 'storage': self.paths.binding(), 'source_hashes': source_hashes or {}})

    def work_path(self, attempt_id):
        path = self.paths.workspace / 'work' / safe_id(attempt_id)
        if path.resolve() != path:
            raise ValueError('Symlinked work location')
        return path

    def start_attempt(self, run_id, stage, owner, retry_of=None, lease_seconds=3600):
        duration(lease_seconds)
        if not stage or not owner:
            raise ValueError('Stage and owner are required')
        with self.transaction():
            self._run(run_id)
            if retry_of and self._read('attempts', retry_of, 'started')['run_id'] != run_id:
                raise ValueError('Retry belongs to another run')
            return self._start_attempt_locked(run_id, stage, owner, retry_of, lease_seconds)

    def _active_attempt(self, identity, lease_token=None):
        data = self._read('attempts', identity, 'started')
        self._run(data['run_id'])
        if self._path('attempts', identity, 'outcome').exists():
            raise ValueError('Attempt has ended')
        self._check_lease(identity, lease_token)
        return data

    def object_path(self, sha256):
        if not re.fullmatch('[0-9a-f]{64}', sha256):
            raise ValueError('Invalid object digest')
        path = self.paths.objects / sha256[:2] / sha256
        if path.resolve() != path:
            raise ValueError('Symlinked object storage')
        return path

    def _claim_objects(self):
        self.paths.objects.mkdir(parents=True, exist_ok=True)
        path = self.paths.objects / '_owner.json'
        identity = {'project': str(self.paths.project), 'project_id': self.config.get('project', {}).get('id'),
                    'storage': self.paths.binding()}
        if path.is_symlink():
            raise ValueError('Symlinked object owner')
        if not path.exists():
            try:
                self._write_path(path, identity)
            except (FileExistsError, ValueError):
                if not path.exists():
                    raise
        owner = json.loads(path.read_text())
        try:
            if owner.get('project') != identity['project'] or owner.get('project_id') != identity['project_id']:
                raise ValueError('Object project identity changed')
            self.resolve_storage_binding(owner.get('storage'))
        except ValueError as error:
            raise ValueError('Object storage is owned by another workspace; shared storage is unsupported') from error

    def register(self, attempt_id, source, role, media_type=None, partial=False, inputs=None, logical_path=None, lease_token=None):
        source = Path(source)
        if logical_path is not None:
            logical_path = relative_name(logical_path)
        if source.is_symlink() or not source.is_file():
            raise ValueError('Artifact must be a regular file')
        with self.transaction():
            attempt = self._active_attempt(attempt_id, lease_token)
            for identity in inputs or []:
                self.verify_artifact(identity)
            # Hash the staged bytes, not a mutable producer file.
            self._claim_objects()
            fd, tmp = tempfile.mkstemp(dir=self.paths.objects)
            try:
                with os.fdopen(fd, 'wb') as stream, source.open('rb') as original:
                    shutil.copyfileobj(original, stream); stream.flush(); os.fsync(stream.fileno())
                staged = Path(tmp); sha = digest(staged); destination = self.object_path(sha)
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(staged, destination)
                except FileExistsError:
                    if digest(destination) != sha:
                        raise ValueError('Object integrity failure')
                self._check_lease(attempt_id, lease_token)
                return self._record('artifacts', {'id': identifier(), 'run_id': attempt['run_id'],
                    'attempt_id': attempt_id, 'sha256': sha, 'size_bytes': staged.stat().st_size,
                    'role': role, 'media_type': media_type or mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
                    'workspace_path': source.resolve().relative_to(self.paths.workspace).as_posix()
                        if source.resolve().is_relative_to(self.paths.workspace / 'work') else None,
                    'name': source.name, 'partial': bool(partial), 'inputs': inputs or [], 'logical_path': logical_path})
            finally:
                Path(tmp).unlink(missing_ok=True)

    def verify_artifact(self, identity):
        data = self._read('artifacts', identity)
        path = self.object_path(data['sha256'])
        if not path.is_file() or path.stat().st_size != data['size_bytes'] or digest(path) != data['sha256']:
            raise ValueError('Artifact integrity failure')
        return data

    def finish_attempt(self, identity, status, reason=None, lease_token=None):
        if status not in ('succeeded', 'failed', 'cancelled', 'interrupted'):
            raise ValueError('Invalid attempt outcome')
        if status != 'succeeded' and not reason:
            raise ValueError('Unsuccessful attempts require a reason')
        with self.transaction():
            data = self._active_attempt(identity, lease_token)
            return self._record('attempts', {'id': identity, 'run_id': data['run_id'],
                'status': status, 'reason': reason}, 'outcome')

    def select(self, run_id, artifacts):
        if not artifacts or len(set(artifacts)) != len(artifacts):
            raise ValueError('Candidate requires unique ordered artifacts')
        with self.transaction():
            self._run(run_id)
            for identity in artifacts:
                data = self.verify_artifact(identity)
                if data['run_id'] != run_id or data['partial']:
                    raise ValueError('Cross-run or partial artifact cannot be selected')
                outcome = self._path('attempts', data['attempt_id'], 'outcome')
                if not outcome.exists() or self._read('attempts', data['attempt_id'], 'outcome')['status'] != 'succeeded':
                    raise ValueError('Artifact producer must have succeeded')
            return self._record('candidates', {'id': identifier(), 'run_id': run_id, 'artifacts': artifacts})

    def status(self, run_id):
        run = self._run(run_id)
        attempts = []
        for path in sorted((self.paths.workspace / 'records' / 'attempts').glob('*/started.json')):
            data = json.loads(path.read_text())
            if data['run_id'] == run_id:
                outcome = path.with_name('outcome.json')
                lease = self._lease(data['id'])
                attempts.append({**data, 'lease': {key: lease[key] for key in ('owner', 'generation', 'expires_at')},
                                 'outcome': json.loads(outcome.read_text()) if outcome.exists() else None})
        attempts.sort(key=lambda data: data['created_at'])
        return {'run': run, 'attempts': attempts, 'remote_verified': False}

    def inventory(self):
        work = self.paths.workspace / 'work'
        bindings = {}
        for path in (self.paths.workspace / 'records/artifacts').glob('*.json'):
            artifact = self._read('artifacts', path.stem)
            if artifact.get('workspace_path'):
                name = relative_name(artifact['workspace_path'])
                bindings.setdefault(str(self.paths.workspace / name), set()).add(artifact['sha256'])
        registered, changed, unknown = [], [], []
        files, links = files_without_links(work)
        for path in files + links:
            name = str(path)
            if name not in bindings:
                unknown.append(name)
            elif path.is_symlink() or path.resolve() != path or digest(path) not in bindings[name]:
                changed.append(name)
            else:
                registered.append(name)
        return {**self._object_inventory(), 'registered_files': sorted(registered), 'changed_files': sorted(changed),
                'unregistered_files': sorted(unknown), 'cleanup_executed': False}

    def git_policy(self, media_mode='git'):
        if media_mode not in ('git', 'lfs', 'external'):
            raise ValueError('Unknown media storage mode')
        root = self.paths.project
        def relative(path):
            return path.relative_to(root).as_posix() if path.is_relative_to(root) else None
        def escape_pattern(value):
            return ''.join(('\\' + char) if char in '\\*?[]!#' else char for char in value)
        ignores = []
        for path in (self.paths.workspace, self.paths.objects):
            if path == self.paths.objects and path.is_relative_to(self.paths.workspace):
                continue
            name = relative(path)
            if name:
                ignores.append('/' + escape_pattern(name) + '/')
        attributes = []
        releases = relative(self.paths.releases)
        if media_mode in ('git', 'lfs') and releases is None:
            raise ValueError('Git media archive must be inside project')
        if media_mode == 'lfs':
            pattern = escape_pattern(releases) + '/**/media/**'
            if ' ' in releases:
                pattern = json.dumps(releases + '/**/media/**')
            attributes.append(pattern + ' filter=lfs diff=lfs merge=lfs -text')
        return {'gitignore': ignores, 'gitattributes': attributes,
                'tracked_roots': [relative(p) for p in (self.paths.releases, self.paths.publications) if relative(p)],
                'media_mode': media_mode, 'applied': False}
