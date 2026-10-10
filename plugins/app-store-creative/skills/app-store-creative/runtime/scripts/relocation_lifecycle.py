"""Exact, reviewable relocation plans before copying or changing bindings."""
from pathlib import Path
from contextlib import contextmanager
import stat
import hashlib
import shutil
import os

from inventory_lifecycle import files_without_links


class RelocationOperations:
    def relocated_object_status(self, plan_id):
        from relocation_object_observations import inspect
        return inspect(self, plan_id)

    def _sync_configuration_directory(self):
        directory_fd = os.open(self.config_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

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
        for intent_path in (self.paths.workspace / 'records/relocations').glob('*/switch-intent.json'):
            identity = intent_path.parent.name
            intent = self._read('relocations', identity, 'switch-intent')
            if intent.get('receipt', {}).get('from') != binding:
                continue
            fence_path = self._path('storage-fences', key, identity)
            if not fence_path.exists() and not fence_path.is_symlink():
                raise ValueError('Storage write fence is missing for relocation; use relocation recovery')
        for path in directory.glob('*.json'):
            fence = self._read('storage-fences', key, path.stem)
            if fence.get('from') != binding or fence.get('config_path') != str(self.config_path):
                raise ValueError('Storage write fence scope is invalid')
            release_path = self._path('storage-fence-releases', key, path.stem)
            if release_path.exists():
                release = self._read('storage-fence-releases', key, path.stem)
                if release.get('reverse_id'):
                    try:
                        reverse = self._read('relocations', release['reverse_id'], 'switched')
                    except FileNotFoundError as error:
                        raise ValueError('Reverse storage fence release is pending activation') from error
                    if (reverse.get('status') == 'SWITCHED' and reverse.get('to') == binding
                            and reverse.get('reverse_of') == path.stem
                            and reverse.get('config_path') == str(self.config_path)
                            and reverse.get('project_id') == self.config.get('project', {}).get('id')
                            and release.get('forward_id') == path.stem
                            and release.get('fence_sha256') == hashlib.sha256(canonical(fence)).hexdigest()
                            and release.get('reverse_switch_sha256') == hashlib.sha256(canonical(reverse)).hexdigest()):
                        continue
                    raise ValueError('Reverse storage fence release evidence is invalid')
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
        from maintenance_fences import check_relocation
        check_relocation(self)
        from artifact_lifecycle import canonical, digest
        from delivery_lifecycle import verify_archive
        for path in (self.paths.workspace / 'records/attempts').glob('*/started.json'):
            if not self._path('attempts', path.parent.name, 'outcome').exists():
                raise ValueError('Relocation is blocked by an active attempt')
        inventory = self._object_inventory()
        if inventory['observation_errors']:
            raise ValueError('Relocation requires complete storage observations')
        if any(inventory['objects'][key] for key in ('corrupt', 'missing', 'corrupt_quarantine_files')):
            raise ValueError('Relocation requires intact registered objects and quarantine evidence')
        for path in (self.paths.workspace / 'records/deliveries').glob('*.json'):
            delivery = self._read('deliveries', path.stem)
            verify_archive(self.delivery_path(delivery), delivery['manifest_sha256'])
        return self._relocation_file_snapshot()

    def _owned_relocation_marker(self, path, root):
        """Only omit a control marker bound to a known published relocation root."""
        import json
        if path != root / '.relocation-owner.json':
            return False
        try:
            marker = json.loads(path.read_text())
        except ValueError:
            return False
        if not isinstance(marker, dict) or set(marker) != {'plan_id', 'group'}:
            return False
        try:
            plan = self._read('relocations', marker['plan_id'])
            if plan.get('operation') not in ('relocation-plan', 'reverse-relocation-plan'):
                return False
            groups = self._relocation_layout(plan)[1]
            return groups.get(marker['group']) == root
        except (ValueError, OSError, KeyError, TypeError):
            return False

    def _relocation_file_snapshot(self, labels=None):
        from artifact_lifecycle import canonical, digest
        stages = []
        for path in (self.paths.workspace / 'records/relocations').glob('*/prepare-intent.json'):
            stages.extend(Path(value) for value in self._read('relocations', path.parent.name, 'prepare-intent')['staging'].values())
        files = []
        for label, root in self.paths.binding().items():
            if labels is not None and label not in labels:
                continue
            root = Path(root)
            paths, links = files_without_links(root, strict=True)
            links = [path for path in links if not any(path.is_relative_to(stage) for stage in stages)]
            if links:
                raise ValueError('Relocation source contains unsafe symlinks')
            for path in paths:
                if any(path.is_relative_to(stage) for stage in stages):
                    continue
                name = path.relative_to(root).as_posix()
                if self._owned_relocation_marker(path, root):
                    continue
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

    def _assert_relocation_local_absence(self):
        from configuration_layers import local_path_for
        try:
            local_path_for(self.config_path).lstat()
        except FileNotFoundError:
            return
        raise ValueError('Host-local configuration appeared during relocation; layer-aware recovery is required')

    def _relocation_configuration_change(self, storage, allow_local=False):
        from configuration_layers import load, local_path_for, plan_storage_change
        try:
            self.config_path.lstat()
        except FileNotFoundError:
            try:
                local_path_for(self.config_path).lstat()
            except FileNotFoundError:
                return None
            raise ValueError('Host-local configuration requires a shared configuration authority')
        layers = load(self.paths.project, self.config_path)
        if layers.paths.binding() != self.paths.binding():
            raise ValueError('Host-local configuration requires layer-aware storage binding')
        change = plan_storage_change(layers, storage)
        if change['target_path'] != str(self.config_path) and not allow_local:
            raise ValueError('Host-local relocation requires a layer-aware switch executor')
        return change

    def plan_relocation(self, storage):
        from artifact_lifecycle import canonical, digest, identifier
        from forward_source_copies import identities
        with self.transaction():
            config = self._live_configuration()
            target, target_config = self._relocation_targets(storage, config)
            configuration_change = self._relocation_configuration_change(storage, allow_local=True)
            if configuration_change:
                from configuration_layers import owning_document
                target_config = owning_document(self.paths.project, self.config_path, configuration_change)['effective_config']
            files, snapshot_hash = self._relocation_snapshot()
            config_file_hash = digest(Path(configuration_change['target_path'])) if configuration_change else (digest(self.config_path) if self.config_path.is_file() else None)
            return self._record('relocations', {'id': identifier(), 'operation': 'relocation-plan',
                'from': self.paths.binding(), 'to': target.binding(), 'requested_storage': storage,
                'source_root_identities': identities(self.paths.binding()),
                'source_config_sha256': hashlib.sha256(canonical(config)).hexdigest(),
                'source_config_file_sha256': config_file_hash,
                'configuration_change': configuration_change,
                'target_config_sha256': hashlib.sha256(canonical(target_config)).hexdigest(),
                'config_path': str(self.config_path), 'files': files, 'snapshot_sha256': snapshot_hash,
                'logical_bytes': sum(item['size_bytes'] for item in files),
                'relocation_executed': False, 'source_deletion_authorized': False,
                'scope': 'Local copy and verification plan; execution and rebinding are separate'})

    def _reverse_relocation_evidence(self, forward_id):
        from artifact_lifecycle import Lifecycle, canonical, digest
        import base64
        import json
        forward = self._read('relocations', forward_id)
        if (forward.get('operation') not in ('relocation-plan', 'reverse-relocation-plan')
                or forward.get('to') != self.paths.binding()):
            raise ValueError('Reverse relocation requires the active forward destination')
        status = self.relocation_status(forward_id)
        if status['status'] != 'SWITCHED' or status['target_activation_status'] != 'VERIFIED':
            raise ValueError('Reverse relocation requires verified forward activation')
        intent = self._read('relocations', forward_id, 'switch-intent')
        source_bytes = base64.b64decode(intent['source_config_base64'], validate=True)
        if hashlib.sha256(source_bytes).hexdigest() != forward['source_config_file_sha256']:
            raise ValueError('Reverse relocation source configuration backup is invalid')
        from configuration_layers import owning_document
        forward_authority = owning_document(self.paths.project, self.config_path, forward['configuration_change'])
        if source_bytes != forward_authority['source_bytes']:
            raise ValueError('Reverse owning source backup differs')
        original = Lifecycle(self.paths.project, forward_authority['source_effective_config'], self.config_path)
        if original.paths.binding() != forward['from']:
            raise ValueError('Reverse relocation original storage binding changed')
        original._assert_paths()
        source_key = hashlib.sha256(canonical(forward['from'])).hexdigest()
        old_fence = original._read('storage-fences', source_key, forward_id)
        if (old_fence != self._read('storage-fences', source_key, forward_id)
                or old_fence.get('from') != forward['from']
                or old_fence.get('relocation_id') != forward_id
                or old_fence.get('project_id') != self.config.get('project', {}).get('id')
                or old_fence.get('prepared_sha256') != hashlib.sha256(canonical(self._read('relocations', forward_id, 'prepared'))).hexdigest()
                or old_fence.get('config_path') != str(self.config_path)):
            raise ValueError('Reverse relocation preserved source fence changed')
        changed_roots = {key for key in forward['from'] if forward['from'][key] != forward['to'][key]}
        preserved, _ = original._relocation_file_snapshot(changed_roots)
        fence_path = original._path('storage-fences', source_key, forward_id).relative_to(original.paths.workspace).as_posix()
        preserved = [item for item in preserved
                     if not (item['root'] == 'workspace' and item['path'] == fence_path)]
        expected = [item for item in forward['files'] if item['root'] in changed_roots]
        if preserved != expected:
            raise ValueError('Reverse relocation preserved source differs from forward snapshot')
        config = self._live_configuration()
        target_config = json.loads(canonical(config))
        target_config['storage'] = original.config.get('storage', {})
        configuration_change = self._relocation_configuration_change(target_config['storage'], allow_local=True)
        target_config = owning_document(self.paths.project, self.config_path, configuration_change)['effective_config']
        target = Lifecycle(self.paths.project, target_config, self.config_path)
        if target.paths.binding() != forward['from']:
            raise ValueError('Reverse relocation restored storage configuration differs')
        files, snapshot = self._relocation_snapshot()
        layout = {'id': forward_id, 'from': self.paths.binding(), 'to': forward['from']}
        groups = self._relocation_layout(layout)[1]
        occupied = {}
        for key, path in groups.items():
            if path.resolve() != path or path.is_symlink() or (path.exists() and not path.is_dir()):
                raise ValueError('Reverse relocation destination directory identity is unavailable')
            info = path.stat() if path.exists() else None
            occupied[key] = [info.st_dev, info.st_ino] if info is not None else None
        return {'forward_id': forward_id, 'from': self.paths.binding(), 'to': forward['from'],
                'configuration_change': configuration_change,
                'files': files, 'snapshot_sha256': snapshot,
                'preserved_source_sha256': hashlib.sha256(canonical(preserved)).hexdigest(),
                'occupied_root_identities': occupied,
                'config_path': str(self.config_path),
                'source_config_file_sha256': digest(Path(configuration_change['target_path'])),
                'source_config_sha256': hashlib.sha256(canonical(config)).hexdigest(),
                'target_config_sha256': hashlib.sha256(canonical(target_config)).hexdigest(),
                'requested_storage': target_config['storage']}

    def plan_reverse_relocation(self, forward_id):
        from artifact_lifecycle import identifier
        with self.transaction():
            evidence = self._reverse_relocation_evidence(forward_id)
            return self._record('relocations', {'id': identifier(),
                'operation': 'reverse-relocation-plan', **evidence,
                'logical_bytes': sum(item['size_bytes'] for item in evidence['files']),
                'relocation_executed': False, 'source_deletion_authorized': False,
                'scope': 'Occupied original roots verified; execution is a separate operation'})

    def switch_reverse_relocation(self, plan_id, actor, reason):
        from reverse_relocation import switch, record_interruption
        try:
            return switch(self, plan_id, actor, reason)
        except BaseException as error:
            record_interruption(self, plan_id, error)
            raise

    def resume_reverse_relocation(self, plan_id, actor, reason):
        from reverse_relocation import resume, record_interruption
        try:
            return resume(self, plan_id, actor, reason)
        except BaseException as error:
            record_interruption(self, plan_id, error)
            raise

    def rollback_reverse_relocation(self, plan_id, actor, reason):
        from reverse_relocation import rollback, record_interruption
        try:
            return rollback(self, plan_id, actor, reason)
        except BaseException as error:
            record_interruption(self, plan_id, error)
            raise

    def _verify_reverse_relocation_locked(self, plan_id):
        plan = self._read('relocations', plan_id)
        if plan.get('operation') != 'reverse-relocation-plan':
            raise ValueError('Expected a reverse relocation plan')
        if self._path('relocations', plan_id, 'cancelled').exists():
            raise ValueError('Reverse relocation plan was cancelled')
        evidence = self._reverse_relocation_evidence(plan['forward_id'])
        if plan.get('occupied_root_identities') != evidence['occupied_root_identities']:
            raise ValueError('Reverse relocation destination directory identity changed')
        if any(plan.get(key) != value for key, value in evidence.items()):
            raise ValueError('Reverse relocation plan is stale; create a new plan')
        return {'plan_id': plan_id, 'status': 'READY',
                'files_verified': len(evidence['files']), 'relocation_executed': False}

    def verify_reverse_relocation_plan(self, plan_id):
        with self.transaction():
            return self._verify_reverse_relocation_locked(plan_id)

    def prepare_reverse_relocation(self, plan_id, actor, reason):
        if self._read('relocations', plan_id).get('operation') != 'reverse-relocation-plan':
            raise ValueError('Expected a reverse relocation plan')
        return self.prepare_relocation(plan_id, actor, reason)

    def relocation_status(self, plan_id):
        """Read operation evidence even when the current storage is fenced."""
        plan = self._read('relocations', plan_id)
        if (plan.get('operation') not in ('relocation-plan', 'reverse-relocation-plan')
                or plan.get('config_path') != str(self.config_path)
                or self.paths.binding() not in (plan.get('from'), plan.get('to'))):
            raise ValueError('Relocation status scope changed')
        records = {}
        for name in ('prepare-intent', 'prepared', 'prepare-outcome', 'switch-intent',
                     'switch-outcome', 'switched', 'rollback-intent', 'rollback', 'cancelled'):
            path = self._path('relocations', plan_id, name)
            if path.exists() or path.is_symlink():
                records[name] = self._read('relocations', plan_id, name)
        expected = {'prepared': 'PREPARED', 'prepare-outcome': 'PREPARATION_FAILED',
                    'switch-outcome': 'SWITCH_INTERRUPTED', 'switched': 'SWITCHED',
                    'rollback': 'ROLLED_BACK', 'cancelled': 'CANCELLED'}
        for name, value in expected.items():
            allowed = {value, 'CANCELLED_PARTIAL'} if name == 'cancelled' else {value}
            if name in records and records[name].get('status') not in allowed:
                raise ValueError('Relocation receipt status is invalid')
        if 'cancelled' in records:
            retained = records['cancelled'].get('retained_paths', [])
            if not isinstance(retained, list) or any(not isinstance(path, str) for path in retained):
                raise ValueError('Relocation retained path evidence is invalid')
        if 'switched' in records:
            receipt = records['switched']
            if (receipt.get('from') != plan['from'] or receipt.get('to') != plan['to']
                    or receipt.get('config_path') != str(self.config_path)
                    or receipt.get('project_id') != self.config.get('project', {}).get('id')):
                raise ValueError('Relocation switch receipt scope changed')
        status = 'PLANNED'
        for name, state in (('prepare-intent', 'PREPARING'),
                            ('prepare-outcome', 'PREPARATION_FAILED'), ('prepared', 'PREPARED'),
                            ('switch-intent', 'SWITCHING'), ('switch-outcome', 'SWITCH_INTERRUPTED'),
                            ('rollback-intent', 'ROLLING_BACK'), ('switched', 'SWITCHED'),
                            ('rollback', 'ROLLED_BACK'), ('cancelled', 'CANCELLED')):
            if name in records:
                status = records[name]['status'] if name == 'cancelled' else state
        errors = []
        try:
            self._check_storage_activation()
            self._check_storage_write_fence()
        except (ValueError, OSError) as error:
            errors.append(str(error))
        target_status = 'NOT_SWITCHED'
        target_errors = []
        if status == 'SWITCHED':
            from artifact_lifecycle import Lifecycle, canonical
            try:
                intent = records.get('switch-intent')
                if not isinstance(intent, dict) or not isinstance(intent.get('target_config'), dict):
                    raise ValueError('Relocation target configuration evidence is missing')
                if intent.get('plan_sha256') != hashlib.sha256(canonical(plan)).hexdigest():
                    raise ValueError('Relocation plan differs from switch intent')
                if intent.get('receipt') != records['switched']:
                    raise ValueError('Relocation switch receipt differs from intent')
                target_config = intent['target_config']
                if hashlib.sha256(canonical(target_config)).hexdigest() != plan['target_config_sha256']:
                    raise ValueError('Relocation target configuration evidence differs from plan')
                target = Lifecycle(self.paths.project, target_config, self.config_path)
                if target.paths.binding() != plan['to']:
                    raise ValueError('Relocation target binding differs from plan')
                target._assert_paths()
                key = hashlib.sha256(canonical(plan['to'])).hexdigest()
                activation = target._read('storage-activations', key)
                if activation.get('relocation_id') != plan_id:
                    raise ValueError('Relocation target activation belongs to another operation')
                target._check_storage_activation()
                if target._read('relocations', plan_id, 'switched') != records['switched']:
                    raise ValueError('Relocation source and target switch receipts differ')
                changes = intent['storage_controls']
                expected_changes = self._relocation_control_changes(plan, records['switched'],
                    {category: item['before'] for category, item in changes.items()})
                if canonical(changes) != canonical(expected_changes):
                    raise ValueError('Relocation control journal differs from switch scope')
                for category, change in expected_changes.items():
                    if target._read(category, change['key']) != change['after']:
                        raise ValueError('Published relocation control differs: ' + category)
                target_status = 'VERIFIED'
            except (ValueError, OSError, KeyError, TypeError) as error:
                target_status = 'FAIL'
                target_errors.append(str(error))
        recovery = ('REVERSE_RELOCATION_REQUIRED' if status == 'SWITCHED' else
                    'RESUME_OR_ROLLBACK' if status in ('SWITCHING', 'SWITCH_INTERRUPTED', 'ROLLING_BACK') else
                    'RECOVER_OR_CANCEL' if status in ('PREPARING', 'PREPARATION_FAILED') else 'NONE')
        return {'id': plan_id, 'status': status, 'from': plan['from'], 'to': plan['to'],
                'current_binding': self.paths.binding(), 'current_binding_writable': not errors,
                'errors': errors, 'recovery': recovery, 'source_deleted': False,
                'retained_paths': records.get('cancelled', {}).get('retained_paths', []),
                'target_activation_status': target_status,
                'target_activation_errors': target_errors,
                'media_integrity_verified': False,
                'scope': 'Read-only operation evidence; use verification before execution'}

    def _verify_relocation_locked(self, plan_id):
        from artifact_lifecycle import canonical, digest
        plan = self._read('relocations', plan_id)
        if plan.get('operation') == 'reverse-relocation-plan':
            return self._verify_reverse_relocation_locked(plan_id)
        if self._path('relocations', plan_id, 'cancelled').exists():
            raise ValueError('Relocation plan was cancelled')
        if plan.get('operation') != 'relocation-plan' or plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
            raise ValueError('Relocation plan storage or configuration scope changed')
        from forward_source_copies import identities
        if plan.get('source_root_identities') != identities(self.paths.binding()):
            raise ValueError('Relocation source directory identity changed')
        config = self._live_configuration()
        target, target_config = self._relocation_targets(plan['requested_storage'], config)
        if ('configuration_change' not in plan or
                self._relocation_configuration_change(plan['requested_storage'], allow_local=True) != plan['configuration_change']):
            raise ValueError('Relocation configuration layers are stale or differ; create a new plan')
        if plan['configuration_change']:
            from configuration_layers import owning_document
            target_config = owning_document(self.paths.project, self.config_path, plan['configuration_change'])['effective_config']
        files, snapshot_hash = self._relocation_snapshot()
        change = plan['configuration_change']
        actual = digest(Path(change['target_path'])) if change else (digest(self.config_path) if self.config_path.is_file() else None)
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

    def _verify_staging_root_proofs(self, prepared):
        from artifact_lifecycle import canonical
        plan = self._read('relocations', prepared['id'])
        _, _, staging = self._relocation_layout(plan)
        hashes = prepared.get('staging_root_proof_sha256')
        if not isinstance(hashes, dict) or set(hashes) != set(staging):
            raise ValueError('Staging root proof hash bindings are missing')
        for key, path in staging.items():
            proof = self._read('relocations', prepared['id'], 'staging-root-' + key)
            if (proof.get('group') != key or proof.get('path') != path
                    or hashlib.sha256(canonical(proof)).hexdigest() != hashes[key]):
                raise ValueError('Staging root proof hash differs from prepared receipt')

    def _verify_prepared_relocation(self, prepared):
        from artifact_lifecycle import digest
        self._verify_staging_root_proofs(prepared)
        plan = self._read('relocations', prepared['id'])
        if plan.get('operation') == 'relocation-plan':
            from reverse_relocation import _identity
            _, _, staging = self._relocation_layout(plan)
            if prepared.get('staging') != staging:
                raise ValueError('Prepared staging directory identity scope changed')
            for key, name in staging.items():
                proof = self._read('relocations', prepared['id'], 'staging-root-' + key)
                expected = proof.get('directory_identity')
                if (proof.get('group') != key or proof.get('path') != name
                        or not isinstance(expected, list) or len(expected) != 2
                        or any(type(value) is not int or value < 0 for value in expected)
                        or _identity(Path(name)) != expected):
                    raise ValueError('Prepared staging directory identity changed')
        if plan.get('operation') == 'reverse-relocation-plan':
            _, groups, staging = self._relocation_layout(plan)
            roots = prepared.get('exchange_roots')
            if not isinstance(roots, list) or len(roots) != len(groups):
                raise ValueError('Reverse exchange directory identity evidence is missing')
            seen = set()
            for root in roots:
                if not isinstance(root, dict) or root.get('group') not in groups or root['group'] in seen:
                    raise ValueError('Reverse exchange directory identity scope is invalid')
                key = root['group']; seen.add(key)
                if root.get('staging') != staging[key] or root.get('destination') != str(groups[key]):
                    raise ValueError('Reverse exchange directory identity path changed')
                for label, path in (('staging', Path(staging[key])), ('destination', groups[key])):
                    expected_identity = root.get(label + '_identity')
                    if label == 'destination' and expected_identity is None:
                        if path.exists() or path.is_symlink() or path.resolve() != path:
                            raise ValueError('Reverse exchange destination directory identity changed')
                        continue
                    if (not isinstance(expected_identity, list) or len(expected_identity) != 2
                            or any(type(value) is not int or value < 0 for value in expected_identity)
                            or path.resolve() != path or not path.is_dir()):
                        raise ValueError('Reverse exchange directory identity is invalid')
                    actual = path.stat()
                    if expected_identity != [actual.st_dev, actual.st_ino]:
                        raise ValueError('Reverse exchange directory identity changed')
                expected_operation = 'PUBLISH' if root['destination_identity'] is None else 'EXCHANGE'
                if root.get('operation') != expected_operation:
                    raise ValueError('Reverse exchange directory identity operation changed')
                if root['destination_identity'] != plan['occupied_root_identities'][key]:
                    raise ValueError('Reverse exchange destination directory identity differs from plan')
        from quarantine_locations import verify_prepared
        verify_prepared(self, plan, prepared)
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
        if plan.get('operation') not in ('relocation-plan', 'reverse-relocation-plan') or plan['from'] != self.paths.binding():
            raise ValueError('Relocation plan scope changed')
        policy = staging_policy(self._relocation_layout(plan)[2])
        if plan.get('operation') in ('relocation-plan', 'reverse-relocation-plan') and plan.get('configuration_change') is not None:
            from storage_git_policy import repository_for, ignore_pattern
            from configuration_layers import owning_document
            authority = owning_document(self.paths.project, self.config_path, plan['configuration_change'])
            target = authority['path']
            policy['configuration_target'] = str(target)
            policy['configuration_layer'] = 'project' if target == self.config_path else 'local'
            staged = target.with_name('.' + target.name + '.creative-' + plan_id + '.tmp')
            from configuration_installation import installation_paths
            _, installation_temporary, installation_record = installation_paths(self, plan_id)
            _, restoration_temporary, restoration_record = installation_paths(self, plan_id, restoring=True)
            protected = [staged, *(self._path('relocations', plan_id, 'configuration-' + name)
                                 for name in ('intent', 'created', 'prepared')), installation_temporary,
                         installation_record, restoration_temporary, restoration_record]
            if target != self.config_path:
                protected.append(target)
            policy['configuration_staging'] = str(staged)
            policy['configuration_records'] = [str(path) for path in (*protected[1:4], installation_record, restoration_record)]
            policy['configuration_installation_staging'] = str(installation_temporary)
            policy['configuration_restoration_staging'] = str(restoration_temporary)
            for path in protected:
                repository = repository_for(path)
                if repository is None:
                    continue
                pattern = ignore_pattern(path.relative_to(repository).as_posix()).removesuffix('/')
                entry = next((item for item in policy['repositories'] if item['root'] == str(repository)), None)
                if entry is None:
                    entry = {'root':str(repository), 'gitignore_path':str(repository / '.gitignore'), 'patterns':[]}
                    policy['repositories'].append(entry)
                entry['patterns'].append(pattern)
                policy['gitignore'].append(pattern)
        return policy

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
                    info = root.stat()
                    self._record('relocations', {'id': plan_id, 'group': key, 'path': str(root),
                        'directory_identity': [info.st_dev, info.st_ino]}, 'staging-root-' + key)
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
                if plan.get('operation') == 'reverse-relocation-plan':
                    prepared['exchange_roots'] = []
                    for key, final in groups.items():
                        staged_info = Path(staging[key]).stat()
                        final_info = final.stat() if final.exists() else None
                        if final_info is not None and staged_info.st_dev != final_info.st_dev:
                            raise ValueError('Reverse exchange requires one filesystem per root')
                        prepared['exchange_roots'].append({'group': key, 'staging': staging[key],
                            'destination': str(final),
                            'operation': 'EXCHANGE' if final_info is not None else 'PUBLISH',
                            'staging_identity': [staged_info.st_dev, staged_info.st_ino],
                            'destination_identity': [final_info.st_dev, final_info.st_ino] if final_info is not None else None})
                from quarantine_locations import capture
                prepared['quarantine_locations'] = capture(self, plan)
                prepared['staging_root_proof_sha256'] = {
                    key: hashlib.sha256(canonical(self._read('relocations', plan_id, 'staging-root-' + key))).hexdigest()
                    for key in staging}
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
            if self._path('relocations', plan_id, 'prepared').exists():
                self._verify_staging_root_proofs(self._read('relocations', plan_id, 'prepared'))
            markers = {}
            owners = {}
            for key, value in staging.items():
                root = Path(value)
                if not root.exists() and not root.is_symlink():
                    continue
                proof_path = self._path('relocations', plan_id, 'staging-root-' + key)
                if not proof_path.exists() or proof_path.is_symlink():
                    raise ValueError('Relocation staging creation ownership is unavailable')
                proof = self._read('relocations', plan_id, 'staging-root-' + key)
                info = root.lstat()
                if (proof.get('path') != str(root) or proof.get('group') != key
                        or proof.get('directory_identity') != [info.st_dev, info.st_ino]):
                    raise ValueError('Relocation staging directory identity changed')
                marker = root / '.relocation-owner.json'
                expected = canonical({'plan_id': plan_id, 'group': key})
                if root.resolve() != root or marker.resolve() != marker or not marker.is_file() or marker.read_bytes() != expected:
                    raise ValueError('Relocation staging ownership cannot be verified')
                markers[root] = marker
                owners[root] = ([info.st_dev, info.st_ino], expected)
            def assert_owned_root(root):
                info = root.lstat()
                marker = markers[root]
                identity, expected = owners[root]
                if (root.resolve() != root or [info.st_dev, info.st_ino] != identity
                        or marker.resolve() != marker or not marker.is_file()
                        or marker.read_bytes() != expected):
                    raise ValueError('Relocation staging ownership or directory identity changed during cancellation')
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
            for root in markers:
                assert_owned_root(root)
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
                    assert_owned_root(root)
                    path.unlink(); removed.append(str(path))
            for directory in sorted(directories, key=lambda value: len(value.parts), reverse=True):
                root = next(root for root in markers if directory.is_relative_to(root))
                assert_owned_root(root)
                if directory.resolve() == directory and directory.is_dir():
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
            retained = []
            for root, marker in markers.items():
                assert_owned_root(root)
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

    def _relocation_control_changes(self, plan, receipt, predecessors=None):
        from artifact_lifecycle import canonical
        changes = {}
        for category, binding in [('storage-activations', plan['to']), ('storage-bindings', plan['from'])]:
            key = hashlib.sha256(canonical(binding)).hexdigest()
            if predecessors is None:
                path = self._path(category, key)
                previous = self._read(category, key) if path.exists() or path.is_symlink() else None
            else:
                previous = predecessors[category]
            relative = 'records/' + category + '/' + key + '.json'
            planned = next((item for item in plan['files']
                            if item['root'] == 'workspace' and item['path'] == relative), None)
            if previous is None:
                if planned is not None:
                    raise ValueError('Relocation control predecessor is missing')
            else:
                encoded = canonical(previous)
                if (planned is None or planned['sha256'] != hashlib.sha256(encoded).hexdigest()
                        or planned['size_bytes'] != len(encoded)):
                    raise ValueError('Relocation control predecessor differs from plan')
                old = self._read('relocations', previous['relocation_id'], 'switched')
                field = 'to' if category == 'storage-activations' else 'from'
                if (old.get('status') != 'SWITCHED' or old.get(field) != binding
                        or previous.get(field) != binding or previous.get('to') != old.get('to')
                        or old.get('config_path') != str(self.config_path)
                        or old.get('project_id') != self.config.get('project', {}).get('id')
                        or hashlib.sha256(canonical(old)).hexdigest() != previous.get('switch_sha256')):
                    raise ValueError('Relocation previous control receipt differs')
            after = {'schema_version': 1, 'created_at': receipt['created_at'], 'id': key,
                     'to': plan['to'], 'relocation_id': plan['id'],
                     'switch_sha256': hashlib.sha256(canonical(receipt)).hexdigest()}
            if category == 'storage-bindings':
                after['from'] = plan['from']
            changes[category] = {'key': key, 'before': previous, 'after': after}
        return changes

    def _verified_relocation_controls(self, plan, intent):
        from artifact_lifecycle import canonical
        if plan['operation'] == 'relocation-plan':
            from forward_source_copies import verify_capture
            verify_capture(self, plan, intent)
        changes = intent['storage_controls']
        expected = self._relocation_control_changes(plan, intent['receipt'],
                    {category: item['before'] for category, item in changes.items()})
        if canonical(changes) != canonical(expected):
            raise ValueError('Relocation control journal differs from verified scope')
        return changes

    def switch_relocation(self, plan_id, actor, reason):
        """Internal switch entry; recovery must be available before exposing a CLI."""
        from artifact_lifecycle import canonical, digest, now
        from delivery_lifecycle import commit_directory
        from storage_control_projection import publish
        import json
        import tempfile
        import base64
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation switch requires actor and reason')
        if self._read('relocations', plan_id).get('operation') != 'relocation-plan':
            raise ValueError('Reverse relocation switching requires a dedicated execution operation')
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
            from configuration_layers import owning_document
            authority = owning_document(self.paths.project, self.config_path, plan['configuration_change'])
            configuration_target = authority['path']
            target_config = authority['effective_config']
            from configuration_preparation import (prepare_storage_change,
                verify_prepared_storage_change, _RelocationConfigurationCore)
            configuration_core = _RelocationConfigurationCore(self)
            configuration_prepared = prepare_storage_change(configuration_core,
                plan['configuration_change'], plan_id, actor, reason)
            if Path(configuration_prepared['staged_path']).read_bytes() != authority['target_bytes']:
                raise ValueError('Prepared relocation configuration differs from target')
            from forward_source_copies import capture
            source_copies = capture(self, plan)
            receipt = {'schema_version': 1, 'created_at': now(), 'id': plan_id,
                'status': 'SWITCHED', 'from': plan['from'], 'to': plan['to'],
                'config_path': str(self.config_path), 'project_id': self.config.get('project', {}).get('id'),
                'actor': actor, 'reason': reason, 'source_deleted': False,
                'target_config_sha256': plan['target_config_sha256'],
                'source_copies_sha256': hashlib.sha256(canonical(source_copies)).hexdigest()}
            changes = self._relocation_control_changes(plan, receipt)
            self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                'storage_controls': changes, 'source_copies': source_copies,
                'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(),
                'prepared_sha256': hashlib.sha256(canonical(prepared)).hexdigest(),
                'receipt': receipt, 'target_config': target_config, 'staging': staging,
                'configuration_prepared': configuration_prepared,
                'source_config_base64': base64.b64encode(authority['source_bytes']).decode('ascii'),
                'source_config_mode': authority['mode']}, 'switch-intent')
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
                change = changes['storage-activations']
                publish(self, workspace, plan_id, 'storage-activations', change['key'], change['before'], change['after'])
                for key, final in groups.items():
                    commit_directory(Path(staging[key]), final)
                for item in plan['files']:
                    path = Path(plan['to'][item['root']]) / item['path']
                    activation_relative = 'records/storage-activations/' + target_key + '.json'
                    if item['root'] == 'workspace' and item['path'] == activation_relative:
                        if path.resolve() != path or path.read_bytes() != canonical(changes['storage-activations']['after']):
                            raise ValueError('Published relocation activation differs')
                        continue
                    if path.resolve() != path or not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                        raise ValueError('Published relocation bytes failed verification')
                verify_prepared_storage_change(configuration_core, plan['configuration_change'], plan_id)
                target_bytes = Path(configuration_prepared['staged_path']).read_bytes()
                if target_bytes != authority['target_bytes']:
                    raise ValueError('Prepared configuration changed before replacement')
                from configuration_installation import (prepare_configuration_installation,
                    verify_configuration_installation, transfer_installation_proof)
                temporary = prepare_configuration_installation(self, plan_id)
                verify_prepared_storage_change(configuration_core, plan['configuration_change'], plan_id)
                os.replace(temporary, configuration_target)
                verify_configuration_installation(self, plan_id, installed=True)
                self._sync_configuration_directory()
                transfer_installation_proof(self, plan_id, Path(plan['to']['workspace']))
                target_records = Path(plan['to']['workspace']) / 'records'
                source_key = hashlib.sha256(canonical(plan['from'])).hexdigest()
                change = changes['storage-bindings']
                publish(self, Path(plan['to']['workspace']), plan_id, 'storage-bindings', change['key'], change['before'], change['after'])
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
        from storage_control_projection import restore
        import base64
        import fcntl
        import json
        import tempfile
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation rollback requires actor and reason')
        with recovery_lock(self):
            plan = self._read('relocations', plan_id)
            if plan.get('operation') != 'relocation-plan':
                raise ValueError('Use rollback-reverse-relocate for reverse plans')
            if plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
                raise ValueError('Rollback source scope changed')
            from configuration_layers import owning_document
            authority = owning_document(self.paths.project, self.config_path, plan['configuration_change'])
            configuration_target = authority['path']
            if configuration_target == self.config_path:
                self._assert_relocation_local_absence()
            intent = self._read('relocations', plan_id, 'switch-intent')
            changes = self._verified_relocation_controls(plan, intent)
            source_key = hashlib.sha256(canonical(plan['from'])).hexdigest()
            fence_path = self._path('storage-fences', source_key, plan_id)
            if not fence_path.exists() and not fence_path.is_symlink():
                # Intent may survive process death before the initial fence commit.
                # Full pre-switch checks refuse reconstruction after source changes.
                self._fence_relocation_locked(plan_id)
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
            if configuration_target.is_symlink() or not configuration_target.is_file():
                raise ValueError('Rollback configuration location changed')
            actual = configuration_target.read_bytes()
            if actual not in (source, authority['target_bytes']):
                raise ValueError('Rollback configuration was edited; refusing overwrite')
            from configuration_layers import verify_storage_change, verify_local_git_protection
            from configuration_installation import (installation_paths,
                prepare_configuration_installation, verify_configuration_installation)
            _, restoration_temporary, restoration_record = installation_paths(self, plan_id, restoring=True)
            for path in (restoration_temporary, restoration_record):
                verify_local_git_protection(path)
            if actual == source:
                if restoration_record.exists() or restoration_record.is_symlink():
                    verify_configuration_installation(self, plan_id, installed=True, restoring=True)
                else:
                    verify_storage_change(self.paths.project, self.config_path, plan['configuration_change'])
            else:
                verify_configuration_installation(self, plan_id, installed=True)
            files, _ = self._relocation_snapshot()
            owned = {self._path('storage-fences', source_key, plan_id).relative_to(self.paths.workspace).as_posix()}
            target_key = hashlib.sha256(canonical(plan['to'])).hexdigest()
            if plan['to']['workspace'] == plan['from']['workspace']:
                owned.add(self._path('storage-activations', target_key).relative_to(self.paths.workspace).as_posix())
                owned.add(self._path('storage-bindings', source_key).relative_to(self.paths.workspace).as_posix())
            files = [item for item in files if not (item['root'] == 'workspace' and item['path'] in owned)]
            if files != [item for item in plan['files'] if not (item['root'] == 'workspace' and item['path'] in owned)]:
                raise ValueError('Rollback source changed; preserve fenced storage for investigation')
            if not self._path('relocations', plan_id, 'rollback-intent').exists():
                self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason,
                    'source_config_sha256': plan['source_config_file_sha256']}, 'rollback-intent')
            if actual != source:
                verify_configuration_installation(self, plan_id, installed=True)
                temporary = prepare_configuration_installation(self, plan_id, restoring=True)
                verify_configuration_installation(self, plan_id, installed=True)
                os.replace(temporary, configuration_target)
                verify_configuration_installation(self, plan_id, installed=True, restoring=True)
            if restoration_record.exists() or restoration_record.is_symlink():
                verify_configuration_installation(self, plan_id, installed=True, restoring=True)
            else:
                verify_storage_change(self.paths.project, self.config_path, plan['configuration_change'])
            self._sync_configuration_directory()
            if plan['to']['workspace'] == plan['from']['workspace']:
                for category, change in changes.items():
                    restore(self, self.paths.workspace, plan_id, category, change['key'], change['before'], change['after'])
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
        from storage_control_projection import publish
        from storage_git_policy import verify_staging_ignored
        import base64
        import fcntl
        import json
        import tempfile
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Relocation resume requires actor and reason')
        with recovery_lock(self):
            plan = self._read('relocations', plan_id)
            if plan.get('operation') != 'relocation-plan':
                raise ValueError('Use resume-reverse-relocate for reverse plans')
            if plan['from'] != self.paths.binding() or plan['config_path'] != str(self.config_path):
                raise ValueError('Resume source scope changed')
            from configuration_layers import owning_document
            authority = owning_document(self.paths.project, self.config_path, plan['configuration_change'])
            configuration_target = authority['path']
            if configuration_target == self.config_path:
                self._assert_relocation_local_absence()
            if self._path('relocations', plan_id, 'rollback-intent').exists():
                raise ValueError('Rollback started; forward resume is forbidden')
            intent = self._read('relocations', plan_id, 'switch-intent')
            receipt = intent['receipt']; receipt_hash = hashlib.sha256(canonical(receipt)).hexdigest()
            changes = self._verified_relocation_controls(plan, intent)
            target_records = Path(plan['to']['workspace']) / 'records'
            switched = target_records / 'relocations' / plan_id / 'switched.json'
            if switched.exists():
                if switched.resolve() != switched or switched.read_bytes() != canonical(receipt):
                    raise ValueError('Resume switch receipt integrity failure')
                status = self.relocation_status(plan_id)
                if status['target_activation_status'] != 'VERIFIED':
                    raise ValueError('Completed resume target control activation verification failed: ' + '; '.join(status['target_activation_errors']))
                return receipt
            source_key = hashlib.sha256(canonical(plan['from'])).hexdigest()
            target_key = hashlib.sha256(canonical(plan['to'])).hexdigest()
            prepared = self._read('relocations', plan_id, 'prepared')
            self._verify_staging_root_proofs(prepared)
            fence_path = self._path('storage-fences', source_key, plan_id)
            if not fence_path.exists() and not fence_path.is_symlink():
                # Intent may survive process death before the initial fence commit.
                # Full pre-switch checks refuse reconstruction after source changes.
                self._fence_relocation_locked(plan_id)
            fence = self._read('storage-fences', source_key, plan_id)
            if fence['prepared_sha256'] != hashlib.sha256(canonical(prepared)).hexdigest():
                raise ValueError('Resume fence evidence changed')
            original = base64.b64decode(intent['source_config_base64'], validate=True)
            target_config = authority['target_bytes']
            if (hashlib.sha256(canonical(intent['target_config'])).hexdigest() != plan['target_config_sha256']
                    or receipt.get('from') != plan['from'] or receipt.get('to') != plan['to']
                    or receipt.get('config_path') != str(self.config_path)
                    or fence.get('from') != plan['from'] or fence.get('relocation_id') != plan_id):
                raise ValueError('Resume switch evidence changed')
            if hashlib.sha256(original).hexdigest() != plan['source_config_file_sha256']:
                raise ValueError('Resume configuration backup integrity failure')
            if configuration_target.is_symlink() or not configuration_target.is_file():
                raise ValueError('Resume configuration location changed')
            actual_config = configuration_target.read_bytes()
            if actual_config not in (original, target_config):
                raise ValueError('Resume configuration was edited')
            from configuration_preparation import verify_prepared_storage_change, _RelocationConfigurationCore
            configuration_core = _RelocationConfigurationCore(self)
            configuration_prepared = self._read('relocations', plan_id, 'configuration-prepared')
            if intent.get('configuration_prepared') != configuration_prepared:
                raise ValueError('Resume configuration preparation receipt differs')
            from configuration_installation import (prepare_configuration_installation,
                verify_configuration_installation, transfer_installation_proof)
            if actual_config == original:
                verify_prepared_storage_change(configuration_core, plan['configuration_change'], plan_id)
                installation = self._path('relocations', plan_id, 'configuration-installation')
                if installation.exists() or installation.is_symlink():
                    verify_configuration_installation(self, plan_id)
            else:
                verify_configuration_installation(self, plan_id, installed=True)
            files, _ = self._relocation_snapshot()
            owned = {self._path('storage-fences', source_key, plan_id).relative_to(self.paths.workspace).as_posix()}
            if plan['to']['workspace'] == plan['from']['workspace']:
                owned.update(self._path(category, key).relative_to(self.paths.workspace).as_posix()
                             for category, key in [('storage-activations', target_key), ('storage-bindings', source_key)])
            if ([item for item in files if not (item['root'] == 'workspace' and item['path'] in owned)]
                    != [item for item in plan['files'] if not (item['root'] == 'workspace' and item['path'] in owned)]):
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
                proof = self._read('relocations', plan_id, 'staging-root-' + key)
                info = root.stat()
                expected_identity = proof.get('directory_identity')
                if (proof.get('group') != key or proof.get('path') != staging[key]
                        or not isinstance(expected_identity, list) or len(expected_identity) != 2
                        or any(type(value) is not int or value < 0 for value in expected_identity)
                        or expected_identity != [info.st_dev, info.st_ino]):
                    raise ValueError('Resume staging directory identity changed')
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
            from quarantine_locations import verify_at
            verify_at(self, prepared, workspace)
            source_records = self.paths.workspace / 'records'
            records, links = files_without_links(source_records)
            if links:
                raise ValueError('Resume source contains unsafe record links')
            controls = {workspace / 'records' / path.relative_to(source_records): path.read_bytes() for path in records}
            activation = workspace / 'records/storage-activations' / (target_key + '.json')
            binding = workspace / 'records/storage-bindings' / (source_key + '.json')
            transitions = {workspace / 'records' / category / (change['key'] + '.json'): change
                           for category, change in changes.items()}
            histories = {workspace / 'records/relocations' / plan_id / 'control-history' / category / (change['key'] + '.json')
                         for category, change in changes.items()}
            allowed = set(expected) | set(controls) | set(transitions) | histories
            for root in locations.values():
                actual, links = files_without_links(root)
                if links or any(path not in allowed for path in actual):
                    raise ValueError('Resume root contains unexpected files or links')
            for path, item in expected.items():
                if path in transitions:
                    continue
                if path.resolve() != path or not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                    raise ValueError('Resume copied bytes failed verification')
            for path, data in controls.items():
                if path in transitions:
                    continue
                if path.exists() and (path.resolve() != path or path.read_bytes() != data):
                    raise ValueError('Resume operation evidence changed')
            for path, change in transitions.items():
                if path.resolve() != path or path.is_symlink():
                    raise ValueError('Resume control contains aliases')
                stored = path.read_bytes() if path.exists() else None
                previous = None if change['before'] is None else canonical(change['before'])
                if stored not in (previous, canonical(change['after'])):
                    raise ValueError('Resume control evidence changed')
            if not self._path('relocations', plan_id, 'resume-intent').exists():
                self._record('relocations', {'id': plan_id, 'actor': actor, 'reason': reason}, 'resume-intent')
            for path, data in controls.items():
                if path in transitions:
                    continue
                if not path.exists():
                    self._write_path(path, json.loads(data))
            change = changes['storage-activations']
            publish(self, workspace, plan_id, 'storage-activations', change['key'], change['before'], change['after'])
            for key, final in groups.items():
                if locations[key] != final:
                    commit_directory(locations[key], final)
            if configuration_target.read_bytes() != actual_config:
                raise ValueError('Resume configuration changed during recovery')
            if actual_config != target_config:
                verify_prepared_storage_change(configuration_core, plan['configuration_change'], plan_id)
                if Path(configuration_prepared['staged_path']).read_bytes() != target_config:
                    raise ValueError('Resume prepared configuration bytes changed')
                temporary = prepare_configuration_installation(self, plan_id)
                verify_prepared_storage_change(configuration_core, plan['configuration_change'], plan_id)
                os.replace(temporary, configuration_target)
            verify_configuration_installation(self, plan_id, installed=True)
            self._sync_configuration_directory()
            transfer_installation_proof(self, plan_id, Path(plan['to']['workspace']))
            binding = target_records / 'storage-bindings' / (source_key + '.json')
            change = changes['storage-bindings']
            publish(self, Path(plan['to']['workspace']), plan_id, 'storage-bindings', change['key'], change['before'], change['after'])
            self._write_path(switched, receipt)
            if target_records != source_records and not self._path('relocations', plan_id, 'switched').exists():
                self._record('relocations', receipt, 'switched')
            return receipt


@contextmanager
def recovery_lock(core):
    """Lock the existing recovery authority without creating or following replacements."""
    import fcntl
    core._assert_paths()
    path = core.paths.workspace / 'write.lock'
    if path.resolve() != path or path.is_symlink():
        raise ValueError('Unsafe recovery lock')
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Recovery lock must be a regular file')
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'r+b') as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
            raise ValueError('Recovery lock identity changed')
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError('Recovery lock identity changed')
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def recovery_source(root, config_path, workspace, plan_id):
    """Read and verify the original authority before opening recovery writes."""
    from artifact_lifecycle import Lifecycle, canonical, safe_id
    import base64
    import json
    from configuration_layers import _read_regular, _document
    root = Path(root).resolve(); config_path = Path(config_path).resolve()
    workspace = Path(workspace)
    if workspace.resolve() != workspace or not workspace.is_dir():
        raise ValueError('Recovery source workspace must be a real directory')
    plan_id = safe_id(plan_id)
    def read(relative):
        path = workspace / relative
        if path.resolve() != path or not path.is_file():
            raise ValueError('Recovery source metadata is missing or symlinked')
        return _document(_read_regular(path))
    plan = read('records/relocations/' + plan_id + '.json')
    intent = read('records/relocations/' + plan_id + '/switch-intent.json')
    source = base64.b64decode(intent['source_config_base64'], validate=True)
    if hashlib.sha256(source).hexdigest() != plan['source_config_file_sha256']:
        raise ValueError('Recovery configuration backup integrity failure')
    if not isinstance(plan.get('configuration_change'), dict):
        raise ValueError('Recovery configuration layer authority is required')
    from configuration_layers import owning_document
    authority = owning_document(root, config_path, plan['configuration_change'])
    if source != authority['source_bytes']:
        raise ValueError('Recovery owning configuration backup differs')
    config = authority['source_effective_config']
    if hashlib.sha256(canonical(config)).hexdigest() != plan['source_config_sha256']:
        raise ValueError('Recovery configuration identity changed')
    core = Lifecycle(root, config, config_path)
    if (plan.get('id') != plan_id or plan.get('operation') not in ('relocation-plan', 'reverse-relocation-plan')
            or plan['from'] != core.paths.binding() or core.paths.workspace != workspace
            or plan['config_path'] != str(config_path)
            or read('configuration-authority.json') != {'config_path': str(config_path)}
            or read('owner.json') != {'project': str(root), 'project_id': config.get('project', {}).get('id')}):
        raise ValueError('Recovery source authority or project scope changed')
    return core
