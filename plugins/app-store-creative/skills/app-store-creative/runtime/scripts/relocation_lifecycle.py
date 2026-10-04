"""Exact, reviewable relocation plans before copying or changing bindings."""
from pathlib import Path
import hashlib
import shutil
import os

from inventory_lifecycle import files_without_links


class RelocationOperations:
    def _check_storage_activation(self):
        from artifact_lifecycle import canonical
        binding = self.paths.binding()
        key = hashlib.sha256(canonical(binding)).hexdigest()
        path = self._path('storage-activations', key)
        if not path.exists() and not path.is_symlink():
            for intent_path in (self.paths.workspace / 'records/relocations').glob('*/switch-intent.json'):
                intent = self._read('relocations', intent_path.parent.name, 'switch-intent')
                if intent.get('receipt', {}).get('to') == binding:
                    raise ValueError('Relocation destination is inactive; activation metadata is missing')
            return
        activation = self._read('storage-activations', key)
        try:
            switched = self._read('relocations', activation['relocation_id'], 'switched')
        except (KeyError, FileNotFoundError) as error:
            raise ValueError('Relocation destination is inactive; switch recovery is required') from error
        if (activation.get('to') != binding or switched.get('to') != binding
                or switched.get('status') != 'SWITCHED'
                or switched.get('config_path') != str(self.config_path)
                or switched.get('project_id') != self.config.get('project', {}).get('id')
                or hashlib.sha256(canonical(switched)).hexdigest() != activation.get('switch_sha256')):
            raise ValueError('Relocation destination is inactive; activation evidence does not match')

    def _check_storage_write_fence(self):
        from artifact_lifecycle import canonical
        binding = self.paths.binding()
        key = hashlib.sha256(canonical(binding)).hexdigest()
        directory = self.paths.workspace / 'records/storage-fences' / key
        if directory.resolve() != directory:
            raise ValueError('Symlinked storage fence directory')
        for path in directory.glob('*.json'):
            fence = self._read('storage-fences', key, path.stem)
            if fence.get('from') != binding or fence.get('config_path') != str(self.config_path):
                raise ValueError('Storage write fence scope is invalid')
            release_path = self._path('storage-fence-releases', key, path.stem)
            if release_path.exists():
                release = self._read('storage-fence-releases', key, path.stem)
                rollback = self._read('relocations', path.stem, 'rollback')
                if (rollback.get('status') == 'ROLLED_BACK' and rollback.get('from') == binding
                        and release.get('fence_sha256') == hashlib.sha256(canonical(fence)).hexdigest()
                        and release.get('rollback_sha256') == hashlib.sha256(canonical(rollback)).hexdigest()):
                    continue
                raise ValueError('Storage write fence release evidence is invalid')
            raise ValueError('Storage is fenced for relocation; use relocation recovery')

    def _fence_relocation_locked(self, plan_id):
        """Called under the source lock before a switch can expose new roots."""
        from artifact_lifecycle import canonical
        from storage_git_policy import verify_staging_ignored
        self._verify_relocation_locked(plan_id)
        if not self._path('relocations', plan_id, 'prepared').exists():
            raise ValueError('Relocation must be prepared before fencing')
        prepared = self._read('relocations', plan_id, 'prepared')
        verify_staging_ignored(prepared['staging'])
        self._verify_prepared_relocation(prepared)
        binding = self.paths.binding()
        key = hashlib.sha256(canonical(binding)).hexdigest()
        return self._record('storage-fences', {'id': key, 'from': binding,
            'relocation_id': plan_id, 'config_path': str(self.config_path),
            'project_id': self.config.get('project', {}).get('id'),
            'prepared_sha256': hashlib.sha256(canonical(prepared)).hexdigest()}, plan_id)

    def resolve_storage_binding(self, binding):
        """Resolve immutable historical bindings through verified switch receipts."""
        from artifact_lifecycle import canonical
        current = self.paths.binding()
        seen = set()
        while binding != current:
            if not isinstance(binding, dict) or set(binding) != set(current):
                raise ValueError('Invalid storage binding')
            if any(not isinstance(value, str) or not Path(value).is_absolute()
                   or str(Path(value)) != value for value in binding.values()):
                raise ValueError('Invalid storage binding location')
            key = hashlib.sha256(canonical(binding)).hexdigest()
            if key in seen:
                raise ValueError('Storage binding cycle')
            seen.add(key)
            try:
                edge = self._read('storage-bindings', key)
                switched = self._read('relocations', edge['relocation_id'], 'switched')
            except (FileNotFoundError, KeyError) as error:
                raise ValueError('Run storage binding changed; relocation evidence is missing; relocate explicitly') from error
            if (edge.get('id') != key or edge.get('from') != binding
                    or switched.get('status') != 'SWITCHED'
                    or switched.get('from') != binding or switched.get('to') != edge.get('to')
                    or switched.get('project_id') != self.config.get('project', {}).get('id')
                    or switched.get('config_path') != str(self.config_path)
                    or hashlib.sha256(canonical(switched)).hexdigest() != edge.get('switch_sha256')):
                raise ValueError('Storage binding evidence does not match')
            binding = edge['to']
        return binding

    def _relocation_targets(self, storage, config):
        from artifact_lifecycle import canonical, StoragePaths, overlaps
        import json
        if not isinstance(storage, dict):
            raise ValueError('Relocation storage must be an object')
        target_config = json.loads(canonical(config))
        target_config['storage'] = storage
        target = StoragePaths.resolve(self.paths.project, target_config)
        source = self.paths.binding(); destination = target.binding()
        if source == destination:
            raise ValueError('Relocation roots are unchanged')
        for key, name in destination.items():
            if name == source[key]:
                continue
            path = Path(name)
            for source_key, source_name in source.items():
                old = Path(source_name)
                within_retained_workspace = (key == 'objects' and source_key == 'workspace'
                    and destination['workspace'] == source['workspace'] and path.is_relative_to(old))
                if overlaps(path, old) and not within_retained_workspace:
                    raise ValueError('Relocation destination overlaps source storage')
            if path.exists() or path.is_symlink():
                raise ValueError('Relocation destination already exists')
        return target, target_config

    def _relocation_snapshot(self):
        from artifact_lifecycle import canonical, digest
        from delivery_lifecycle import verify_archive
        for path in (self.paths.workspace / 'records/attempts').glob('*/started.json'):
            if not self._path('attempts', path.parent.name, 'outcome').exists():
                raise ValueError('Relocation is blocked by an active attempt')
        inventory = self._object_inventory()
        if any(inventory['objects'][key] for key in ('corrupt', 'missing', 'corrupt_quarantine_files')):
            raise ValueError('Relocation requires intact registered objects and quarantine evidence')
        for path in (self.paths.workspace / 'records/deliveries').glob('*.json'):
            delivery = self._read('deliveries', path.stem)
            verify_archive(self.delivery_path(delivery), delivery['manifest_sha256'])
        stages = []
        for path in (self.paths.workspace / 'records/relocations').glob('*/prepare-intent.json'):
            stages.extend(Path(value) for value in self._read('relocations', path.parent.name, 'prepare-intent')['staging'].values())
        files = []
        for label, root in self.paths.binding().items():
            root = Path(root)
            paths, links = files_without_links(root)
            links = [path for path in links if not any(path.is_relative_to(stage) for stage in stages)]
            if links:
                raise ValueError('Relocation source contains unsafe symlinks')
            for path in paths:
                if any(path.is_relative_to(stage) for stage in stages):
                    continue
                name = path.relative_to(root).as_posix()
                if label == 'workspace':
                    if name == 'write.lock' or name.startswith('records/relocations/'):
                        continue
                    if self.paths.objects.is_relative_to(root) and path.is_relative_to(self.paths.objects):
                        continue
                before = path.stat()
                sha = digest(path)
                after = path.stat()
                if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ValueError('Relocation source changed while hashing')
                files.append({'root': label, 'path': name, 'size_bytes': after.st_size, 'sha256': sha})
        files.sort(key=lambda item: (item['root'], item['path']))
        return files, hashlib.sha256(canonical(files)).hexdigest()

    def plan_relocation(self, storage):
        from artifact_lifecycle import canonical, digest, identifier
        with self.transaction():
            config = self._live_configuration()
            target, target_config = self._relocation_targets(storage, config)
            files, snapshot_hash = self._relocation_snapshot()
            config_file_hash = digest(self.config_path) if self.config_path.is_file() else None
            return self._record('relocations', {'id': identifier(), 'operation': 'relocation-plan',
                'from': self.paths.binding(), 'to': target.binding(), 'requested_storage': storage,
                'source_config_sha256': hashlib.sha256(canonical(config)).hexdigest(),
                'source_config_file_sha256': config_file_hash,
                'target_config_sha256': hashlib.sha256(canonical(target_config)).hexdigest(),
                'config_path': str(self.config_path), 'files': files, 'snapshot_sha256': snapshot_hash,
                'logical_bytes': sum(item['size_bytes'] for item in files),
                'relocation_executed': False, 'source_deletion_authorized': False,
                'scope': 'Local copy and verification plan; execution and rebinding are separate'})

    def _verify_relocation_locked(self, plan_id):
        from artifact_lifecycle import canonical, digest
        plan = self._read('relocations', plan_id)
        if self._path('relocations', plan_id, 'cancelled').exists():
            raise ValueError('Relocation plan was cancelled')
        if plan.get('operation') != 'relocation-plan' or plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
            raise ValueError('Relocation plan storage or configuration scope changed')
        config = self._live_configuration()
        target, target_config = self._relocation_targets(plan['requested_storage'], config)
        files, snapshot_hash = self._relocation_snapshot()
        actual = digest(self.config_path) if self.config_path.is_file() else None
        if (hashlib.sha256(canonical(config)).hexdigest() != plan['source_config_sha256']
                or actual != plan['source_config_file_sha256'] or files != plan['files']
                or snapshot_hash != plan['snapshot_sha256'] or target.binding() != plan['to']
                or hashlib.sha256(canonical(target_config)).hexdigest() != plan['target_config_sha256']):
            raise ValueError('Relocation plan is stale; create a new plan')
        return {'plan_id': plan_id, 'status': 'READY', 'files_verified': len(files),
                'logical_bytes': plan['logical_bytes'], 'relocation_executed': False}

    def verify_relocation_plan(self, plan_id):
        with self.transaction():
            return self._verify_relocation_locked(plan_id)

    def _verify_prepared_relocation(self, prepared):
        from artifact_lifecycle import digest
        expected = set()
        for item in prepared['staged_files']:
            path = Path(item['path'])
            if path.resolve() != path or not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                raise ValueError('Prepared relocation integrity failure')
            expected.add(path)
        actual = set()
        for root in prepared['staging'].values():
            files, links = files_without_links(Path(root))
            if links:
                raise ValueError('Prepared relocation contains unsafe links')
            actual.update(files)
        if actual != expected:
            raise ValueError('Prepared relocation contains unexpected or missing files')

    def _relocation_layout(self, plan):
        changed = {key: Path(value) for key, value in plan['to'].items() if value != plan['from'][key]}
        groups = {key: value for key, value in changed.items()
                  if not any(value != other and value.is_relative_to(other) for other in changed.values())}
        staging = {key: str(value.parent / ('.creative-relocate-' + plan['id'] + '-' + key)) for key, value in groups.items()}
        return changed, groups, staging

    def relocation_git_policy(self, plan_id):
        from storage_git_policy import staging_policy
        plan = self._read('relocations', plan_id)
        if plan.get('operation') != 'relocation-plan' or plan['from'] != self.paths.binding():
            raise ValueError('Relocation plan scope changed')
        return staging_policy(self._relocation_layout(plan)[2])

    def prepare_relocation(self, plan_id, actor, reason):
        from artifact_lifecycle import digest, canonical
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation preparation requires actor and reason')
        with self.transaction():
            self._verify_relocation_locked(plan_id)
            if self._path('relocations', plan_id, 'prepared').exists():
                prepared = self._read('relocations', plan_id, 'prepared')
                from storage_git_policy import verify_staging_ignored
                verify_staging_ignored(prepared['staging'])
                self._verify_prepared_relocation(prepared)
                return prepared
            if self._path('relocations', plan_id, 'prepare-intent').exists():
                raise ValueError('Relocation preparation was interrupted; recovery is required')
            plan = self._read('relocations', plan_id)
            changed, groups, staging = self._relocation_layout(plan)
            from storage_git_policy import verify_staging_ignored
            verify_staging_ignored(staging)
            if any(Path(value).exists() or Path(value).is_symlink() for value in staging.values()):
                raise ValueError('Relocation staging path already exists')
            self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                'staging': staging, 'groups': {key: str(value) for key, value in groups.items()}}, 'prepare-intent')
            staged_files = []
            try:
                for key, value in staging.items():
                    root = Path(value); root.parent.mkdir(parents=True, exist_ok=True); root.mkdir()
                    marker = root / '.relocation-owner.json'
                    with marker.open('xb') as stream:
                        stream.write(canonical({'plan_id': plan_id, 'group': key}))
                    staged_files.append({'path': str(marker), 'size_bytes': marker.stat().st_size, 'sha256': digest(marker)})
                for item in plan['files']:
                    if item['root'] not in changed:
                        continue
                    final = changed[item['root']] / item['path']
                    group = next(key for key, root in groups.items() if final.is_relative_to(root))
                    destination = Path(staging[group]) / final.relative_to(groups[group])
                    source = Path(plan['from'][item['root']]) / item['path']
                    if source.resolve() != source or destination.exists() or destination.is_symlink():
                        raise ValueError('Relocation source or staging path changed')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
                    with os.fdopen(source_fd, 'rb') as input_stream:
                        destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        with os.fdopen(destination_fd, 'wb') as output_stream:
                            shutil.copyfileobj(input_stream, output_stream)
                            output_stream.flush()
                            os.fsync(output_stream.fileno())
                    if destination.resolve() != destination or not destination.is_file() or destination.stat().st_size != item['size_bytes'] or digest(destination) != item['sha256']:
                        raise ValueError('Relocation copied bytes failed verification')
                    staged_files.append({'path': str(destination), 'size_bytes': item['size_bytes'], 'sha256': item['sha256']})
                self._verify_relocation_locked(plan_id)
                prepared = {'id': plan_id, 'status': 'PREPARED', 'actor': actor, 'reason': reason,
                    'staging': staging, 'staged_files': staged_files, 'relocation_executed': False,
                    'source_deleted': False, 'configuration_changed': False}
                self._verify_prepared_relocation(prepared)
                return self._record('relocations', prepared, 'prepared')
            except BaseException as error:
                self._record('relocations', {'id': plan_id, 'status': 'PREPARATION_FAILED',
                    'reason': str(error) or type(error).__name__, 'source_deleted': False}, 'prepare-outcome')
                raise

    def recover_relocation(self, plan_id, actor, reason):
        from artifact_lifecycle import identifier
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation recovery requires actor and reason')
        with self.transaction():
            self._verify_relocation_locked(plan_id)
            if self._path('relocations', plan_id, 'recovery').exists():
                return self._read('relocations', plan_id, 'recovery')
            if self._path('relocations', plan_id, 'prepared').exists():
                raise ValueError('Relocation is already prepared; verify or cancel it')
            if not self._path('relocations', plan_id, 'prepare-intent').exists():
                raise ValueError('Relocation preparation has not started')
            if self._path('relocations', plan_id, 'recovery-intent').exists():
                intent = self._read('relocations', plan_id, 'recovery-intent')
            else:
                intent = self._record('relocations', {'id': plan_id, 'retry_plan_id': identifier(),
                    'actor': actor, 'reason': reason}, 'recovery-intent')
            retry_id = intent['retry_plan_id']
            if not self._path('relocations', retry_id).exists():
                plan = self._read('relocations', plan_id)
                retry = {key: value for key, value in plan.items() if key not in ('id', 'created_at', 'schema_version')}
                retry.update(id=retry_id, retry_of=plan_id)
                self._record('relocations', retry)
            return self._record('relocations', {'id': plan_id, 'retry_plan_id': retry_id,
                'status': 'RECOVERY_PLANNED', 'actor': intent['actor'], 'reason': intent['reason'],
                'source_deleted': False, 'configuration_changed': False}, 'recovery')

    def cancel_relocation(self, plan_id, actor, reason):
        from artifact_lifecycle import canonical, digest
        from storage_git_policy import verify_staging_ignored
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation cancellation requires actor and reason')
        with self.transaction():
            plan = self._read('relocations', plan_id)
            if plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
                raise ValueError('Relocation cancellation scope changed')
            if self._path('relocations', plan_id, 'switch-intent').exists():
                raise ValueError('Relocation switch requires recovery instead of cancellation')
            if self._path('relocations', plan_id, 'cancelled').exists():
                return self._read('relocations', plan_id, 'cancelled')
            changed, groups, staging = self._relocation_layout(plan)
            if self._path('relocations', plan_id, 'prepare-intent').exists():
                intent = self._read('relocations', plan_id, 'prepare-intent')
                if intent['staging'] != staging or intent['groups'] != {key: str(value) for key, value in groups.items()}:
                    raise ValueError('Relocation staging ownership scope changed')
            elif any(Path(value).exists() or Path(value).is_symlink() for value in staging.values()):
                raise ValueError('Relocation staging ownership is unknown')
            verify_staging_ignored(staging)
            markers = {}
            for key, value in staging.items():
                root = Path(value)
                if not root.exists() and not root.is_symlink():
                    continue
                marker = root / '.relocation-owner.json'
                expected = canonical({'plan_id': plan_id, 'group': key})
                if root.resolve() != root or marker.resolve() != marker or not marker.is_file() or marker.read_bytes() != expected:
                    raise ValueError('Relocation staging ownership cannot be verified')
                markers[root] = marker
            expected_files = []
            for item in plan['files']:
                if item['root'] not in changed:
                    continue
                final = changed[item['root']] / item['path']
                group = next(key for key, root in groups.items() if final.is_relative_to(root))
                path = Path(staging[group]) / final.relative_to(groups[group])
                if path.name == '.relocation-owner.json':
                    raise ValueError('Relocation payload conflicts with ownership marker')
                expected_files.append((path, item))
            if not self._path('relocations', plan_id, 'cancel-intent').exists():
                self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                    'staging': staging}, 'cancel-intent')
            removed = []
            directories = set()
            for path, item in expected_files:
                root = next(Path(value) for value in staging.values() if path.is_relative_to(Path(value)))
                if root not in markers:
                    continue
                parent = path.parent
                while parent != root:
                    directories.add(parent); parent = parent.parent
                if path.resolve() == path and path.is_file() and path.stat().st_size == item['size_bytes'] and digest(path) == item['sha256']:
                    path.unlink(); removed.append(str(path))
            for directory in sorted(directories, key=lambda value: len(value.parts), reverse=True):
                if directory.resolve() == directory and directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            retained = []
            for root, marker in markers.items():
                contents = list(root.iterdir())
                if contents == [marker]:
                    marker.unlink(); root.rmdir()
                else:
                    files, links = files_without_links(root)
                    retained.extend(str(path) for path in files + links if path != marker)
                    for parent, dirs, _ in os.walk(root, followlinks=False):
                        dirs[:] = [name for name in dirs if not (Path(parent) / name).is_symlink()]
                        retained.extend(str(Path(parent) / name) for name in dirs)
            return self._record('relocations', {'id': plan_id,
                'status': 'CANCELLED_PARTIAL' if retained else 'CANCELLED',
                'actor': actor, 'reason': reason, 'removed_paths': removed,
                'retained_paths': sorted(set(retained)), 'source_deleted': False,
                'configuration_changed': False}, 'cancelled')

    def switch_relocation(self, plan_id, actor, reason):
        """Internal switch entry; recovery must be available before exposing a CLI."""
        from artifact_lifecycle import canonical, digest, now
        from delivery_lifecycle import commit_directory
        import json
        import tempfile
        import base64
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation switch requires actor and reason')
        with self.transaction():
            self._verify_relocation_locked(plan_id)
            if not self.config_path.is_file() or self.config_path.is_symlink():
                raise ValueError('Relocation switch requires a regular authoritative configuration file')
            plan = self._read('relocations', plan_id)
            if not self._path('relocations', plan_id, 'prepared').exists():
                raise ValueError('Relocation must be prepared before switching')
            prepared = self._read('relocations', plan_id, 'prepared')
            self._verify_prepared_relocation(prepared)
            changed, groups, staging = self._relocation_layout(plan)
            target_config = json.loads(canonical(self._live_configuration()))
            target_config['storage'] = plan['requested_storage']
            receipt = {'schema_version': 1, 'created_at': now(), 'id': plan_id,
                'status': 'SWITCHED', 'from': plan['from'], 'to': plan['to'],
                'config_path': str(self.config_path), 'project_id': self.config.get('project', {}).get('id'),
                'actor': actor, 'reason': reason, 'source_deleted': False,
                'target_config_sha256': plan['target_config_sha256']}
            self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                'receipt': receipt, 'target_config': target_config, 'staging': staging,
                'source_config_base64': base64.b64encode(self.config_path.read_bytes()).decode('ascii'),
                'source_config_mode': self.config_path.stat().st_mode & 0o777}, 'switch-intent')
            self._fence_relocation_locked(plan_id)
            try:
                workspace = Path(plan['to']['workspace'])
                if 'workspace' in changed:
                    group = next(key for key, root in groups.items() if workspace.is_relative_to(root))
                    workspace = Path(staging[group]) / workspace.relative_to(groups[group])
                workspace.mkdir(parents=True, exist_ok=True)
                # Transfer operation evidence excluded from the media snapshot, including the fence.
                source_records = self.paths.workspace / 'records'
                files, links = files_without_links(source_records)
                if links:
                    raise ValueError('Relocation records contain unsafe links')
                for source in files:
                    destination = workspace / 'records' / source.relative_to(source_records)
                    if destination.exists():
                        if destination.resolve() != destination or destination.read_bytes() != source.read_bytes():
                            raise ValueError('Relocation target record differs from source')
                    else:
                        self._write_path(destination, json.loads(source.read_text()))
                target_key = hashlib.sha256(canonical(plan['to'])).hexdigest()
                receipt_hash = hashlib.sha256(canonical(receipt)).hexdigest()
                activation_path = workspace / 'records/storage-activations' / (target_key + '.json')
                self._write_path(activation_path, {'schema_version': 1, 'created_at': now(),
                    'id': target_key, 'to': plan['to'], 'relocation_id': plan_id,
                    'switch_sha256': receipt_hash})
                for key, final in groups.items():
                    commit_directory(Path(staging[key]), final)
                for item in plan['files']:
                    path = Path(plan['to'][item['root']]) / item['path']
                    if path.resolve() != path or not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                        raise ValueError('Published relocation bytes failed verification')
                if digest(self.config_path) != plan['source_config_file_sha256']:
                    raise ValueError('Configuration changed during relocation switch')
                fd, temporary = tempfile.mkstemp(dir=self.config_path.parent)
                try:
                    os.fchmod(fd, self._read('relocations', plan_id, 'switch-intent')['source_config_mode'])
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(canonical(target_config)); stream.flush(); os.fsync(stream.fileno())
                    os.replace(temporary, self.config_path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                target_records = Path(plan['to']['workspace']) / 'records'
                source_key = hashlib.sha256(canonical(plan['from'])).hexdigest()
                edge = {'schema_version': 1, 'created_at': now(), 'id': source_key,
                    'from': plan['from'], 'to': plan['to'], 'relocation_id': plan_id,
                    'switch_sha256': receipt_hash}
                self._write_path(target_records / 'storage-bindings' / (source_key + '.json'), edge)
                self._write_path(target_records / 'relocations' / plan_id / 'switched.json', receipt)
                if target_records != source_records:
                    self._record('relocations', receipt, 'switched')
                return receipt
            except BaseException as error:
                self._record('relocations', {'id': plan_id, 'status': 'SWITCH_INTERRUPTED',
                    'reason': str(error) or type(error).__name__, 'source_deleted': False}, 'switch-outcome')
                raise

    def rollback_relocation(self, plan_id, actor, reason):
        """Recover an interrupted, unactivated switch while preserving all copies."""
        from artifact_lifecycle import canonical, digest
        import base64
        import fcntl
        import json
        import tempfile
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation rollback requires actor and reason')
        self._assert_paths()
        lock = self.paths.workspace / 'write.lock'
        if lock.is_symlink():
            raise ValueError('Symlinked relocation recovery lock')
        with lock.open('a+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            plan = self._read('relocations', plan_id)
            if plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
                raise ValueError('Rollback source scope changed')
            intent = self._read('relocations', plan_id, 'switch-intent')
            source_key = hashlib.sha256(canonical(plan['from'])).hexdigest()
            fence = self._read('storage-fences', source_key, plan_id)
            release_path = self._path('storage-fence-releases', source_key, plan_id)
            if self._path('relocations', plan_id, 'rollback').exists() and release_path.exists():
                self._check_storage_write_fence()
                return self._read('relocations', plan_id, 'rollback')
            switched = Path(plan['to']['workspace']) / 'records/relocations' / plan_id / 'switched.json'
            if switched.exists() or switched.is_symlink():
                raise ValueError('Activated relocation requires a separate reverse relocation')
            source = base64.b64decode(intent['source_config_base64'], validate=True)
            if hashlib.sha256(source).hexdigest() != plan['source_config_file_sha256']:
                raise ValueError('Rollback configuration backup is invalid')
            if self.config_path.is_symlink() or not self.config_path.is_file():
                raise ValueError('Rollback configuration location changed')
            actual = self.config_path.read_bytes()
            if actual not in (source, canonical(intent['target_config'])):
                raise ValueError('Rollback configuration was edited; refusing overwrite')
            files, _ = self._relocation_snapshot()
            owned = {self._path('storage-fences', source_key, plan_id).relative_to(self.paths.workspace).as_posix()}
            target_key = hashlib.sha256(canonical(plan['to'])).hexdigest()
            if plan['to']['workspace'] == plan['from']['workspace']:
                owned.add(self._path('storage-activations', target_key).relative_to(self.paths.workspace).as_posix())
                owned.add(self._path('storage-bindings', source_key).relative_to(self.paths.workspace).as_posix())
            files = [item for item in files if not (item['root'] == 'workspace' and item['path'] in owned)]
            if files != plan['files']:
                raise ValueError('Rollback source changed; preserve fenced storage for investigation')
            if not self._path('relocations', plan_id, 'rollback-intent').exists():
                self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                    'source_config_sha256': plan['source_config_file_sha256']}, 'rollback-intent')
            if actual != source:
                fd, temporary = tempfile.mkstemp(dir=self.config_path.parent)
                try:
                    os.fchmod(fd, intent['source_config_mode'])
                    with os.fdopen(fd, 'wb') as output:
                        output.write(source); output.flush(); os.fsync(output.fileno())
                    os.replace(temporary, self.config_path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            if self._path('relocations', plan_id, 'rollback').exists():
                receipt = self._read('relocations', plan_id, 'rollback')
            else:
                receipt = self._record('relocations', {'id': plan_id, 'status': 'ROLLED_BACK',
                    'from': plan['from'], 'to': plan['to'], 'actor': actor, 'reason': reason,
                    'source_deleted': False, 'target_deleted': False,
                    'source_config_sha256': plan['source_config_file_sha256']}, 'rollback')
            self._record('storage-fence-releases', {'id': source_key, 'relocation_id': plan_id,
                'fence_sha256': hashlib.sha256(canonical(fence)).hexdigest(),
                'rollback_sha256': hashlib.sha256(canonical(receipt)).hexdigest()}, plan_id)
            return receipt

    def resume_relocation(self, plan_id, actor, reason):
        """Resume a fenced switch without replacing existing destination bytes."""
        from artifact_lifecycle import canonical, digest, now
        from delivery_lifecycle import commit_directory
        from storage_git_policy import verify_staging_ignored
        import base64
        import fcntl
        import json
        import tempfile
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation resume requires actor and reason')
        self._assert_paths()
        lock = self.paths.workspace / 'write.lock'
        if lock.is_symlink():
            raise ValueError('Symlinked recovery lock')
        with lock.open('a+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            plan = self._read('relocations', plan_id)
            if plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
                raise ValueError('Resume source scope changed')
            if self._path('relocations', plan_id, 'rollback-intent').exists():
                raise ValueError('Rollback started; forward resume is forbidden')
            intent = self._read('relocations', plan_id, 'switch-intent')
            receipt = intent['receipt']; receipt_hash = hashlib.sha256(canonical(receipt)).hexdigest()
            target_records = Path(plan['to']['workspace']) / 'records'
            switched = target_records / 'relocations' / plan_id / 'switched.json'
            if switched.exists():
                if switched.resolve() != switched or switched.read_bytes() != canonical(receipt):
                    raise ValueError('Resume switch receipt integrity failure')
                return receipt
            source_key = hashlib.sha256(canonical(plan['from'])).hexdigest()
            target_key = hashlib.sha256(canonical(plan['to'])).hexdigest()
            prepared = self._read('relocations', plan_id, 'prepared')
            fence = self._read('storage-fences', source_key, plan_id)
            if fence['prepared_sha256'] != hashlib.sha256(canonical(prepared)).hexdigest():
                raise ValueError('Resume fence evidence changed')
            original = base64.b64decode(intent['source_config_base64'], validate=True)
            target_config = canonical(intent['target_config'])
            if (hashlib.sha256(target_config).hexdigest() != plan['target_config_sha256']
                    or receipt.get('from') != plan['from'] or receipt.get('to') != plan['to']
                    or receipt.get('config_path') != str(self.config_path)
                    or fence.get('from') != plan['from'] or fence.get('relocation_id') != plan_id):
                raise ValueError('Resume switch evidence changed')
            if hashlib.sha256(original).hexdigest() != plan['source_config_file_sha256']:
                raise ValueError('Resume configuration backup integrity failure')
            if self.config_path.is_symlink() or not self.config_path.is_file():
                raise ValueError('Resume configuration location changed')
            actual_config = self.config_path.read_bytes()
            if actual_config not in (original, target_config):
                raise ValueError('Resume configuration was edited')
            files, _ = self._relocation_snapshot()
            owned = {self._path('storage-fences', source_key, plan_id).relative_to(self.paths.workspace).as_posix()}
            if plan['to']['workspace'] == plan['from']['workspace']:
                owned.update(self._path(category, key).relative_to(self.paths.workspace).as_posix()
                             for category, key in [('storage-activations', target_key), ('storage-bindings', source_key)])
            if [item for item in files if not (item['root'] == 'workspace' and item['path'] in owned)] != plan['files']:
                raise ValueError('Resume source changed')
            _, groups, staging = self._relocation_layout(plan)
            verify_staging_ignored(staging)
            locations = {}
            for key, final in groups.items():
                stage = Path(staging[key])
                if (stage.exists() or stage.is_symlink()) and (final.exists() or final.is_symlink()):
                    raise ValueError('Resume stage conflicts with target')
                root = final if final.exists() or final.is_symlink() else stage
                marker = root / '.relocation-owner.json'
                if root.resolve() != root or marker.resolve() != marker or not marker.is_file() or marker.read_bytes() != canonical({'plan_id': plan_id, 'group': key}):
                    raise ValueError('Resume root ownership is invalid')
                locations[key] = root
            def locate(final):
                for key, root in groups.items():
                    if final.is_relative_to(root):
                        return locations[key] / final.relative_to(root)
                return final
            expected = {}
            for item in prepared['staged_files']:
                staged = Path(item['path'])
                key = next(key for key, root in staging.items() if staged.is_relative_to(Path(root)))
                expected[locations[key] / staged.relative_to(Path(staging[key]))] = item
            workspace = locate(Path(plan['to']['workspace']))
            source_records = self.paths.workspace / 'records'
            records, links = files_without_links(source_records)
            if links:
                raise ValueError('Resume source contains unsafe record links')
            controls = {workspace / 'records' / path.relative_to(source_records): path.read_bytes() for path in records}
            activation = workspace / 'records/storage-activations' / (target_key + '.json')
            binding = workspace / 'records/storage-bindings' / (source_key + '.json')
            allowed = set(expected) | set(controls) | {activation, binding}
            for root in locations.values():
                actual, links = files_without_links(root)
                if links or any(path not in allowed for path in actual):
                    raise ValueError('Resume root contains unexpected files or links')
            for path, item in expected.items():
                if path.resolve() != path or not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                    raise ValueError('Resume copied bytes failed verification')
            for path, data in controls.items():
                if path.exists() and (path.resolve() != path or path.read_bytes() != data):
                    raise ValueError('Resume operation evidence changed')
            activation_data = {'schema_version': 1, 'created_at': now(), 'id': target_key,
                'to': plan['to'], 'relocation_id': plan_id, 'switch_sha256': receipt_hash}
            edge = {'schema_version': 1, 'created_at': now(), 'id': source_key, 'from': plan['from'],
                'to': plan['to'], 'relocation_id': plan_id, 'switch_sha256': receipt_hash}
            def validate_existing(path, data):
                if path.exists():
                    stored = json.loads(path.read_text())
                    if path.resolve() != path or any(stored.get(key) != value for key, value in data.items() if key != 'created_at'):
                        raise ValueError('Resume control evidence changed')
            validate_existing(activation, activation_data); validate_existing(binding, edge)
            if not self._path('relocations', plan_id, 'resume-intent').exists():
                self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason}, 'resume-intent')
            for path, data in controls.items():
                if not path.exists():
                    self._write_path(path, json.loads(data))
            if not activation.exists():
                self._write_path(activation, activation_data)
            for key, final in groups.items():
                if locations[key] != final:
                    commit_directory(locations[key], final)
            if self.config_path.read_bytes() != actual_config:
                raise ValueError('Resume configuration changed during recovery')
            if actual_config != target_config:
                fd, temporary = tempfile.mkstemp(dir=self.config_path.parent)
                try:
                    os.fchmod(fd, intent['source_config_mode'])
                    with os.fdopen(fd, 'wb') as output:
                        output.write(target_config); output.flush(); os.fsync(output.fileno())
                    os.replace(temporary, self.config_path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            binding = target_records / 'storage-bindings' / (source_key + '.json')
            if not binding.exists():
                self._write_path(binding, edge)
            self._write_path(switched, receipt)
            if target_records != source_records and not self._path('relocations', plan_id, 'switched').exists():
                self._record('relocations', receipt, 'switched')
            return receipt


def recovery_source(root, config_path, workspace, plan_id):
    """Read and verify the original authority before opening recovery writes."""
    from artifact_lifecycle import Lifecycle, canonical, safe_id
    import base64
    import json
    root = Path(root).resolve(); config_path = Path(config_path).resolve()
    workspace = Path(workspace)
    if workspace.resolve() != workspace or not workspace.is_dir():
        raise ValueError('Recovery source workspace must be a real directory')
    plan_id = safe_id(plan_id)
    def read(relative):
        path = workspace / relative
        if path.resolve() != path or not path.is_file():
            raise ValueError('Recovery source metadata is missing or symlinked')
        return json.loads(path.read_text())
    plan = read('records/relocations/' + plan_id + '.json')
    intent = read('records/relocations/' + plan_id + '/switch-intent.json')
    source = base64.b64decode(intent['source_config_base64'], validate=True)
    if hashlib.sha256(source).hexdigest() != plan['source_config_file_sha256']:
        raise ValueError('Recovery configuration backup integrity failure')
    config = json.loads(source)
    if hashlib.sha256(canonical(config)).hexdigest() != plan['source_config_sha256']:
        raise ValueError('Recovery configuration identity changed')
    core = Lifecycle(root, config, config_path)
    if (plan.get('id') != plan_id or plan.get('operation') != 'relocation-plan'
            or plan['from'] != core.paths.binding() or core.paths.workspace != workspace
            or plan['config_path'] != str(config_path)
            or read('configuration-authority.json') != {'config_path': str(config_path)}
            or read('owner.json') != {'project': str(root), 'project_id': config.get('project', {}).get('id')}):
        raise ValueError('Recovery source authority or project scope changed')
    return core
