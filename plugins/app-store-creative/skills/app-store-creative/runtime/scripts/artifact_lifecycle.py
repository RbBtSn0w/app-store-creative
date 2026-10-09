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
import stat
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


def require_human_authorization(actor, authorization_reference):
    if any(not isinstance(value, str) or not value.strip()
           for value in (actor, authorization_reference)):
        raise ValueError('Explicit human actor and authorization reference are required')


def dependency_closure(identities, load):
    """Traverse dependencies without consuming the interpreter call stack."""
    results = {}; pending = {}; active = set()
    stack = [(identity, False) for identity in reversed(list(identities))]
    while stack:
        identity, exiting = stack.pop()
        if exiting:
            active.remove(identity)
            results[identity] = pending.pop(identity)
            continue
        if identity in results:
            continue
        if identity in active:
            raise ValueError('Artifact dependency cycle')
        record = load(identity)
        active.add(identity); pending[identity] = record
        stack.append((identity, True))
        stack.extend((parent, False) for parent in reversed(record['inputs']))
    return results


def overlaps(a, b):
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


STORAGE_DEFAULTS = {'workspaceRoot': '.creative', 'objectRoot': '.creative/objects',
                    'releaseRoot': 'creative-releases', 'publicationRoot': 'creative-publications'}


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
        defaults = STORAGE_DEFAULTS
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
        from project_identity import require_project_identity
        require_project_identity(config)
        from artifact_policy import resolve
        self.artifact_policy = resolve(config)
        self.paths = StoragePaths.resolve(root, config)
        self.config = json.loads(canonical(config))
        self.config_path = Path(config_path).resolve() if config_path is not None else self.paths.project / 'creative.config.json'
        self._explicit_config_path = config_path is not None
        self._owned_leases = {}
        self._execution_id = identifier()
        from runtime_identity import snapshot
        self._implementation_identity = snapshot()

    @classmethod
    def from_configuration(cls, root, config_path=None):
        from configuration_layers import load, observation
        root = Path(root).resolve()
        layers = load(root, config_path if config_path is not None else root / 'creative.config.json')
        core = cls(root, layers.config, layers.project_path)
        core._configuration_layers = layers
        core._configuration_observation = canonical(observation(layers))
        return core

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
        before = lock.lstat() if lock.exists() else None
        if before is not None and not stat.S_ISREG(before.st_mode):
            raise ValueError('Workspace lock must be a regular file')
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        with os.fdopen(descriptor, 'a+b') as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or (before is not None
                    and (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino))):
                raise ValueError('Workspace lock must remain the same regular file')
            fcntl.flock(stream, fcntl.LOCK_EX)
            current = lock.lstat()
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError('Workspace lock identity changed')
            self._check_storage_write_fence()
            self._check_storage_activation()
            self._live_configuration()
            from configuration_layers import _read_regular
            identity = {'project': str(self.paths.project), 'project_id': self.config.get('project', {}).get('id')}
            if owner.exists():
                if json.loads(_read_regular(owner)) != identity:
                    raise ValueError('Workspace is owned by another project')
            else:
                self._write_path(owner, identity)
            configuration = {'config_path': str(self.config_path)}
            if authority.exists():
                if json.loads(_read_regular(authority)) != configuration:
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
        if path.is_symlink() or path.resolve() != path:
            raise ValueError('Symlinked record')
        from configuration_layers import _read_regular
        data = json.loads(_read_regular(path))
        if (not isinstance(data, dict) or type(data.get('schema_version')) is not int
                or data['schema_version'] != 1):
            raise ValueError('Unsupported record schema')
        if data.get('id') != identity:
            raise ValueError('Record identity differs from requested identity')
        if category == 'remote-observations':
            evidence_hash = data.get('evidence_sha256')
            if not isinstance(evidence_hash, str) or not re.fullmatch('[0-9a-f]{64}', evidence_hash):
                raise ValueError('Missing or invalid observation evidence SHA-256')
        from operation_history import CATEGORIES
        if category in CATEGORIES:
            binding = data.get('_commit_event_id')
            if not isinstance(binding, str) or not re.fullmatch(r'[0-9a-f]{32}', binding):
                raise ValueError('Missing or invalid record commit event binding')
            if category != 'runs':
                entity = {'approvals': 'Approval', 'remote-observations': 'Observation',
                          'observation-evidence': 'Observation evidence', 'attempts': 'Attempt',
                          'artifacts': 'Artifact integrity failure'}.get(category, category)
                try:
                    event = self._read('events', binding)
                except FileNotFoundError as error:
                    raise ValueError(entity + ' commit event is missing') from error
                expected = {'category': category, 'id': identity, 'suffix': suffix,
                            'sha256': hashlib.sha256(canonical(data)).hexdigest()}
                if (event.get('kind') != 'record-commit-intent' or event.get('record') != expected
                        or event.get('project_id') != self.config.get('project', {}).get('id')):
                    raise ValueError(entity + ' commit event binding differs from record bytes')
        return data

    def _write_path(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise ValueError('Immutable record already exists')
        from safe_staging import staged_file
        with staged_file(path.parent) as staged:
            staged.stream.write(canonical(data))
            staged.sync()
            staged.publish(path)

    def _record(self, category, data, suffix=None, precommit=None):
        if not isinstance(data, dict):
            raise ValueError('Unsupported record schema')
        version = data.get('schema_version', 1)
        if type(version) is not int or version != 1:
            raise ValueError('Unsupported record schema')
        data = {'schema_version': 1, 'created_at': now(), **data}
        from operation_history import CATEGORIES, before_commit, sync_directory
        path = self._path(category, data['id'], suffix)
        if path.exists() or path.is_symlink():
            raise ValueError('Immutable record already exists')
        if category in CATEGORIES:
            decisions = self.paths.workspace / 'records/commit-abandonments'
            if decisions.resolve() != decisions or decisions.is_symlink():
                raise ValueError('Unsafe commit abandonment records')
            for decision_path in decisions.glob('*.json'):
                decision = self._read('commit-abandonments', decision_path.stem)
                abandoned = decision.get('record', {})
                if (abandoned.get('category') == category and abandoned.get('id') == data['id']
                        and abandoned.get('suffix') == suffix):
                    raise ValueError('Commit target was explicitly abandoned; use a new identity')
            data['_commit_event_id'] = identifier()
        before_commit(self, category, data, suffix)
        if precommit is not None:
            precommit()
        self._write_path(path, data)
        if category in CATEGORIES:
            sync_directory(path.parent)
            sync_directory(path.parent.parent)
        return data

    def export_external_delivery(self, delivery_id, backend, root):
        from external_delivery_archive import export_managed
        return export_managed(self, delivery_id, backend, root)

    def persist_external_media(self, artifact_id, backend, root):
        from external_media_store import persist_managed
        return persist_managed(self, artifact_id, backend, root)

    def restore_external_media(self, reference_id, backend, root):
        from external_media_store import restore_managed
        return restore_managed(self, reference_id, backend, root)

    def abandon_commit(self, event_id, actor, reason):
        from operation_history import abandon
        return abandon(self, event_id, actor, reason)

    def media_budget(self, candidate_id=None):
        from media_budget import inspect
        return inspect(self, candidate_id)

    def inspect_artifact_policy(self):
        from artifact_policy import inspect
        return inspect(self)

    def operation_journals(self):
        from operation_history import journals
        return journals(self)

    def verify_history(self):
        from operation_history import verify
        return verify(self)

    def _run(self, identity):
        run = self._read('runs', identity)
        workflow = run.get('workflow')
        if (not isinstance(workflow, dict) or set(workflow) != {'name', 'version', 'implementation'}
                or workflow['name'] != 'app-store-creative' or type(workflow['version']) is not int
                or workflow['version'] != 1):
            raise ValueError('Missing or unsupported run workflow snapshot')
        from runtime_identity import validate
        validate(workflow['implementation'])
        if (not isinstance(run.get('config'), dict)
                or hashlib.sha256(canonical(run['config'])).hexdigest() != run.get('config_snapshot_sha256')
                or configuration_identity(run['config']) != run.get('config_sha256')):
            raise ValueError('Run configuration snapshot integrity failure')
        try:
            event = self._read('events', run['_commit_event_id'])
        except FileNotFoundError as error:
            raise ValueError('Run commit event is missing') from error
        expected = {'category': 'runs', 'id': identity, 'suffix': None,
                    'sha256': hashlib.sha256(canonical(run)).hexdigest()}
        if (event.get('kind') != 'record-commit-intent' or event.get('record') != expected
                or event.get('project_id') != self.config['project']['id']):
            raise ValueError('Run commit event binding differs from record bytes')
        self.resolve_storage_binding(run['storage'])
        return run

    def start_run(self, target, source_hashes=None):
        with self.transaction():
            layer_evidence = {}
            if hasattr(self, '_configuration_layers'):
                from configuration_layers import observation
                self._live_configuration()
                layer_evidence = {'configuration_layers':observation(self._configuration_layers),
                                  'project_config_snapshot':json.loads(canonical(self._configuration_layers.project_config))}
            return self._record('runs', {'id': identifier(), 'config': self.config,
                                         'workflow': {'name': 'app-store-creative', 'version': 1,
                                                      'implementation': dict(self._implementation_identity)},
                                         'config_sha256': configuration_identity(self.config),
                                         'config_snapshot_sha256': hashlib.sha256(canonical(self.config)).hexdigest(),
                                         'target': target, 'storage': self.paths.binding(), 'source_hashes': source_hashes or {}, **layer_evidence})

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
            from safe_staging import staged_file
            with staged_file(self.paths.objects) as staged:
                with source.open('rb') as original:
                    shutil.copyfileobj(original, staged.stream)
                sha, size = staged.inspect()
                destination = self.object_path(sha)
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    staged.publish(destination)
                except FileExistsError:
                    if digest(destination) != sha:
                        raise ValueError('Object integrity failure')
                self._check_lease(attempt_id, lease_token)
                return self._record('artifacts', {'id': identifier(), 'run_id': attempt['run_id'],
                    'attempt_id': attempt_id, 'sha256': sha, 'size_bytes': size,
                    'role': role, 'media_type': media_type or mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
                    'workspace_path': source.resolve().relative_to(self.paths.workspace).as_posix()
                        if source.resolve().is_relative_to(self.paths.workspace / 'work') else None,
                    'name': source.name, 'partial': bool(partial), 'inputs': inputs or [], 'logical_path': logical_path},
                    precommit=lambda: self._check_lease(attempt_id, lease_token))

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
                'status': status, 'reason': reason}, 'outcome',
                precommit=lambda: self._check_lease(identity, lease_token))

    def source_eligibility_errors(self, identity):
        try:
            closure = self._closure([identity])
            for record in closure.values():
                outcome_path = self._path('attempts', record['attempt_id'], 'outcome')
                if (record['partial'] or not outcome_path.exists()
                        or self._read('attempts', record['attempt_id'], 'outcome')['status'] != 'succeeded'):
                    return ['Source dependency is partial or its producer has not succeeded: ' + record['id']]
        except (ValueError, OSError) as error:
            return ['Source dependency verification failed: ' + str(error)]
        return []

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
            for identity in artifacts:
                errors = self.source_eligibility_errors(identity)
                if errors:
                    raise ValueError('; '.join(errors))
            return self._record('candidates', {'id': identifier(), 'run_id': run_id, 'artifacts': artifacts})

    def _record_page(self, category, limit=20, cursor=None, suffix=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Record list limit must be an integer between 1 and 100')
        records = [self._read(category, path.parent.name if suffix else path.stem, suffix)
                   for path in (self.paths.workspace / 'records' / category).glob(
                       '*/' + suffix + '.json' if suffix else '*.json')]
        records.sort(key=lambda record: (record['created_at'], record['id']), reverse=True)
        if cursor is not None:
            cursor = safe_id(cursor)
            positions = [index for index, record in enumerate(records) if record['id'] == cursor]
            if not positions:
                raise ValueError('Record list cursor is not a known identity')
            records = records[positions[0] + 1:]
        selected = records[:limit]
        return selected, selected[-1]['id'] if len(records) > limit else None

    def list_runs(self, limit=20, cursor=None):
        selected, cursor = self._record_page('runs', limit, cursor)
        return {'runs': [{key: record[key] for key in ('id', 'created_at', 'target', 'config_sha256')}
                         for record in selected], 'next_cursor': cursor}

    def _approval_status_records(self):
        """Expose damaged records for diagnosis without treating them as authority."""
        from configuration_layers import _read_regular, _document
        result = []
        for path in sorted((self.paths.workspace / 'records/approvals').glob('*.json')):
            try:
                result.append((self._read('approvals', path.stem), []))
            except (ValueError, OSError) as error:
                try:
                    record = _document(_read_regular(path))
                    if record.get('id') != path.stem or type(record.get('schema_version')) is not int or record['schema_version'] != 1:
                        record = {'id': path.stem}
                except (ValueError, OSError):
                    record = {'id': path.stem}
                result.append((record, [str(error)]))
        return result

    def status(self, run_id):
        run = self._run(run_id)
        attempts = []
        for path in sorted((self.paths.workspace / 'records' / 'attempts').glob('*/started.json')):
            data = self._read('attempts', path.parent.name, 'started')
            if data['run_id'] == run_id:
                outcome = path.with_name('outcome.json')
                lease = self._lease(data['id'])
                attempts.append({**data, 'lease': {key: lease[key] for key in ('owner', 'generation', 'expires_at')},
                                 'outcome': self._read('attempts', data['id'], 'outcome')
                                 if outcome.exists() or outcome.is_symlink() else None})
        attempts.sort(key=lambda data: data['created_at'])
        outcomes = {attempt['id']: attempt['outcome'] for attempt in attempts}
        artifacts = []
        for path in sorted((self.paths.workspace / 'records/artifacts').glob('*.json')):
            record = self._read('artifacts', path.stem)
            if record['run_id'] != run_id:
                continue
            try:
                self.verify_artifact(record['id'])
                integrity = 'PASS'
            except (ValueError, OSError):
                integrity = 'FAIL'
            errors = []
            if integrity != 'PASS':
                errors.append('Artifact object is missing or corrupt')
            if record['partial']:
                errors.append('Partial artifacts cannot be selected')
            outcome = outcomes.get(record['attempt_id'])
            if not outcome or outcome['status'] != 'succeeded':
                errors.append('Artifact producer has not succeeded')
            errors.extend(self.source_eligibility_errors(record['id']))
            artifacts.append({**record, 'object_integrity': integrity,
                              'candidate_eligible': not errors, 'eligibility_errors': errors})
        candidates = []
        for path in sorted((self.paths.workspace / 'records/candidates').glob('*.json')):
            candidate = self._read('candidates', path.stem)
            if candidate['run_id'] != run_id:
                continue
            errors = []
            try:
                self._candidate(candidate['id'], allow_discarded=True)
            except (ValueError, OSError) as error:
                errors.append(str(error))
            disposition_path = self._path('candidate-dispositions', candidate['id'])
            disposition = self._read('candidate-dispositions', candidate['id']) if disposition_path.exists() else None
            approvals = []
            for approval, integrity_errors in self._approval_status_records():
                if approval.get('stage') != 'design' or approval.get('candidate_id') != candidate['id']:
                    continue
                binding_errors = list(integrity_errors)
                try:
                    if integrity_errors:
                        raise ValueError('Damaged approval cannot authorize this candidate')
                    _, approved_run, validation = self._validated(candidate['id'], approval.get('validation_id'))
                    self._check_design_approval(candidate['id'], approved_run, validation, approval)
                except (ValueError, OSError) as error:
                    binding_errors.append(str(error))
                approvals.append({**approval, 'binding_status': 'STALE' if binding_errors else 'PASS',
                                  'binding_errors': binding_errors})
            candidates.append({**candidate, 'source_status': 'FAIL' if errors else 'PASS',
                               'source_errors': errors, 'disposition': disposition, 'design_approvals': approvals})
        return {'run': run, 'attempts': attempts, 'artifacts': artifacts,
                'candidates': candidates, 'remote_verified': False}

    def inventory(self):
        work = self.paths.workspace / 'work'
        bindings = {}
        for path in (self.paths.workspace / 'records/artifacts').glob('*.json'):
            artifact = self._read('artifacts', path.stem)
            if artifact.get('workspace_path'):
                name = relative_name(artifact['workspace_path'])
                bindings.setdefault(str(self.paths.workspace / name), set()).add(artifact['sha256'])
        registered, changed, unknown = [], [], []
        from inventory_lifecycle import observe_directory
        work_observation = observe_directory(work)
        files, links, _ = work_observation
        for path in files + links:
            name = str(path)
            if name not in bindings:
                unknown.append(name)
            elif path.is_symlink() or path.resolve() != path or digest(path) not in bindings[name]:
                changed.append(name)
            else:
                registered.append(name)
        from relocation_inventory import inventory as relocation_inventory
        from quarantine_inventory import inventory as quarantine_inventory
        return {**self._object_inventory(work_observation), 'relocation_backups': relocation_inventory(self),
                'quarantine_preparations': quarantine_inventory(self),
                'registered_files': sorted(registered), 'changed_files': sorted(changed),
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
            if any(char.isspace() or char == '"' for char in releases):
                pattern = json.dumps(pattern, ensure_ascii=False)
            attributes.append(pattern + ' filter=lfs diff=lfs merge=lfs -text')
        return {'gitignore': ignores, 'gitattributes': attributes,
                'tracked_roots': [relative(p) for p in (self.paths.releases, self.paths.publications) if relative(p)],
                'media_mode': media_mode, 'applied': False}
