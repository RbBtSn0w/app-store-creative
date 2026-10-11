"""Reference-aware retention with reversible, journaled object quarantine."""
from datetime import datetime, timedelta, timezone
import hashlib
import os


class RetentionOperations:
    def maintenance_status(self, operation_id):
        from maintenance_observations import inspect
        return inspect(self, operation_id)

    def cancel_relocation_quarantine_preparation(self, operation_id, actor, reason):
        from relocation_quarantine import cancel
        return cancel(self, operation_id, actor, reason)

    def purge_relocation(self, plan_id, actor, reason):
        from purge_execution import execute
        return execute(self, plan_id, actor, reason)

    def plan_relocation_purge(self, operation_id, quarantine_days=None):
        if quarantine_days is None:
            quarantine_days = self.artifact_policy['quarantineDays']
        from relocation_purge import plan
        return plan(self, operation_id, quarantine_days)

    def verify_relocation_purge(self, plan_id):
        from relocation_purge import verify
        return verify(self, plan_id)

    def commit_relocation_quarantine(self, operation_id, actor, reason):
        from quarantine_commit import commit
        return commit(self, operation_id, actor, reason)

    def restore_relocation_quarantine(self, operation_id, actor, reason):
        from quarantine_commit import restore
        return restore(self, operation_id, actor, reason)

    def prepare_relocation_quarantine(self, plan_id, actor, reason):
        from relocation_quarantine import prepare
        return prepare(self, plan_id, actor, reason)

    def resume_relocation_quarantine_preparation(self, operation_id, actor, reason):
        from relocation_quarantine import resume
        return resume(self, operation_id, actor, reason)

    def verify_relocation_retention(self, plan_id):
        from relocation_retention import verify
        return verify(self, plan_id)

    def plan_relocation_retention(self, *, retention_days=None):
        if retention_days is None:
            retention_days = self.artifact_policy['trialRetentionDays']
        from relocation_retention import plan
        return plan(self, retention_days)

    def list_maintenance(self, limit=20, cursor=None):
        from operation_history import read_lock
        from contextlib import nullcontext
        lock = self.paths.workspace / 'write.lock'
        with read_lock(self) if lock.exists() or lock.is_symlink() else nullcontext():
            selected, next_cursor = self._record_page('maintenance', limit, cursor)
            entries = []
            for record in selected:
                entry = {key: record[key] for key in ('id', 'created_at', 'operation')}
                entry['objects'] = record.get('objects', [])
                entry['execution_verified'] = False
                entry['recorded_status'] = None
                for suffix in ('outcome', 'restore-intent', 'restored', 'purged'):
                    path = self._path('maintenance', record['id'], suffix)
                    if path.exists() or path.is_symlink():
                        entry['recorded_status'] = self._read('maintenance', record['id'], suffix).get('status')
                entries.append(entry)
            return {'maintenance': entries, 'next_cursor': next_cursor, 'remote_write': False}

    def discard_candidate(self, candidate_id, actor, reason):
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Candidate disposition requires actor and reason')
        with self.transaction():
            candidate = self._read('candidates', candidate_id)
            self._run(candidate['run_id'])
            return self._record('candidate-dispositions', {'id': candidate_id,
                'candidate_id': candidate_id, 'status': 'discarded', 'actor': actor, 'reason': reason})

    def _retention_state(self, retention_days, cutoff, include_missing=False):
        from artifact_lifecycle import canonical
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 0:
            raise ValueError('Retention days must be a nonnegative integer')
        records = self.paths.workspace / 'records'
        from inventory_lifecycle import files_without_links, observe_directory
        observed, links = files_without_links(records, strict=True)
        if links:
            raise ValueError('Retention reference records contain unsafe links')
        _, _, object_error = observe_directory(self.paths.objects)
        if object_error is not None:
            raise ValueError('Retention requires a complete object observation: ' + object_error['reason'])
        paths = sorted(p for p in observed if p.suffix == '.json' and 'maintenance' not in p.relative_to(records).parts)
        fingerprint = hashlib.sha256()
        for path in paths:
            if path.is_symlink() or path.resolve() != path:
                raise ValueError('Symlinked lifecycle record')
            fingerprint.update(canonical([path.relative_to(records).as_posix(), path.read_text()]))
        live_config = self._live_configuration()
        fingerprint.update(canonical(live_config))
        configured_imports = self._configured_imports(live_config)
        artifacts = {p.stem: self._read('artifacts', p.stem) for p in (records / 'artifacts').glob('*.json')}
        protected = self._incident_artifacts()
        for identity in configured_imports:
            protected.add(self._read('imports', identity)['artifact_id'])
        for path in (records / 'imports').glob('*.json'):
            disposition_path = self._path('input-dispositions', path.stem)
            if not disposition_path.exists():
                protected.add(self._read('imports', path.stem)['artifact_id'])
            else:
                disposition = self._read('input-dispositions', path.stem)
                if disposition['status'] != 'discarded' or datetime.fromisoformat(disposition['created_at']) > cutoff:
                    protected.add(self._read('imports', path.stem)['artifact_id'])
        for path in (records / 'observation-evidence').glob('*.json'):
            binding = self._read('observation-evidence', path.stem)
            observation = self._read('remote-observations', binding['observation_id'])
            artifact = artifacts.get(binding['artifact_id'])
            if (not artifact or artifact['role'] != 'observation-evidence'
                    or artifact['sha256'] != observation['evidence_sha256']
                    or binding['evidence_sha256'] != observation['evidence_sha256']
                    or binding['publication_id'] != observation['publication_id']):
                raise ValueError('Observation evidence reference differs from managed artifact')
            summary = self._verify_observation_summary(binding, observation)
            protected.update([artifact['id'], summary['id']])
        candidates = {p.stem: self._read('candidates', p.stem) for p in (records / 'candidates').glob('*.json')}
        retained_candidates = set()
        for identity in candidates:
            disposition = self._path('candidate-dispositions', identity)
            if not disposition.exists():
                retained_candidates.add(identity)
            else:
                data = self._read('candidate-dispositions', identity)
                if data['status'] != 'discarded' or datetime.fromisoformat(data['created_at']) > cutoff:
                    retained_candidates.add(identity)
        for category in ('approvals', 'deliveries'):
            for path in (records / category).glob('*.json'):
                candidate_id = self._read(category, path.stem).get('candidate_id')
                if candidate_id:
                    retained_candidates.add(candidate_id)
        for identity in retained_candidates:
            if identity not in candidates:
                raise ValueError('Missing referenced candidate')
            protected.update(candidates[identity]['artifacts'])
        diagnostic_cutoff = cutoff + timedelta(days=retention_days) - timedelta(days=self.artifact_policy['diagnosticRetentionDays'])
        for identity, artifact in artifacts.items():
            artifact_cutoff = diagnostic_cutoff if artifact['role'] == 'diagnostic' else cutoff
            outcome = self._path('attempts', artifact['attempt_id'], 'outcome')
            if not outcome.exists():
                protected.add(identity)
            elif datetime.fromisoformat(self._read('attempts', artifact['attempt_id'], 'outcome')['created_at']) > artifact_cutoff:
                protected.add(identity)
        from artifact_lifecycle import dependency_closure
        def load(identity):
            if identity not in artifacts:
                raise ValueError('Missing referenced artifact')
            return artifacts[identity]
        protected = set(dependency_closure(sorted(protected), load))
        objects = {}
        for identity, artifact in artifacts.items():
            objects.setdefault(artifact['sha256'], []).append(identity)
        eligible = []
        for sha, identities in sorted(objects.items()):
            if any(identity in protected for identity in identities):
                continue
            path = self.object_path(sha)
            if not path.exists():
                if include_missing:
                    sizes = {artifacts[identity]['size_bytes'] for identity in identities}
                    if len(sizes) != 1:
                        raise ValueError('Conflicting object size records')
                    eligible.append({'sha256': sha, 'size_bytes': sizes.pop(), 'artifacts': sorted(identities)})
                continue
            for identity in identities:
                self.verify_artifact(identity)
            eligible.append({'sha256': sha, 'size_bytes': path.stat().st_size, 'artifacts': sorted(identities)})
        return fingerprint.hexdigest(), eligible

    def plan_cleanup(self, retention_days=None):
        if retention_days is None:
            retention_days = self.artifact_policy['trialRetentionDays']
        from artifact_lifecycle import identifier
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 0:
            raise ValueError('Retention days must be a nonnegative integer')
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with self.transaction():
            fingerprint, objects = self._retention_state(retention_days, cutoff)
            return self._record('maintenance', {'id': identifier(), 'operation': 'cleanup-plan',
                'artifact_policy': self.artifact_policy,
                'retention_days': retention_days, 'cutoff': cutoff.isoformat(), 'references_sha256': fingerprint,
                'storage': self.paths.binding(), 'objects': objects, 'cleanup_executed': False})

    def _quarantine_path(self, identity, sha):
        from artifact_lifecycle import safe_id
        self.object_path(sha)
        path = self.paths.objects / '.quarantine' / safe_id(identity) / sha
        if path.resolve() != path:
            raise ValueError('Symlinked quarantine location')
        return path

    def quarantine_cleanup(self, plan_id, actor, reason):
        from artifact_lifecycle import digest, identifier
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Maintenance requires actor and reason')
        with self.transaction():
            plan = self._read('maintenance', plan_id)
            if plan.get('artifact_policy') != self.artifact_policy:
                raise ValueError('Cleanup plan artifact policy differs')
            if plan.get('operation') != 'cleanup-plan' or plan['storage'] != self.paths.binding():
                raise ValueError('Invalid cleanup plan storage or operation')
            fingerprint, objects = self._retention_state(plan['retention_days'], datetime.fromisoformat(plan['cutoff']))
            if fingerprint != plan['references_sha256'] or objects != plan['objects']:
                raise ValueError('Cleanup plan is stale; create a new plan')
            operation = self._record('maintenance', {'id': identifier(), 'operation': 'quarantine',
                'plan_id': plan_id, 'actor': actor, 'reason': reason, 'objects': objects})
            for item in objects:
                source = self.object_path(item['sha256'])
                destination = self._quarantine_path(operation['id'], item['sha256'])
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.link(source, destination)
                if digest(destination) != item['sha256']:
                    raise ValueError('Quarantine integrity failure')
                source.unlink()
            self._record('maintenance', {'id': operation['id'], 'status': 'quarantined'}, 'outcome')
            return operation

    def restore_cleanup(self, operation_id, actor, reason):
        from artifact_lifecycle import digest
        from maintenance_observations import record_digest
        from operation_history import sync_directory
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Maintenance requires actor and reason')
        with self.transaction():
            operation = self._read('maintenance', operation_id)
            plan = self._read('maintenance', operation['plan_id'])
            if (operation.get('operation') != 'quarantine' or plan.get('operation') != 'cleanup-plan'
                    or plan.get('storage') != self.paths.binding() or plan.get('objects') != operation.get('objects')):
                raise ValueError('Restoration plan or storage binding differs')
            purge = self._path('maintenance', operation_id, 'purge-intent')
            if purge.exists() or purge.is_symlink():
                raise ValueError('Quarantine purge has started; recovery is unavailable')
            intent_path = self._path('maintenance', operation_id, 'restore-intent')
            outcome = self._path('maintenance', operation_id, 'restored')
            binding = {'operation_sha256': record_digest(operation),
                       'plan_sha256': record_digest(plan), 'storage': self.paths.binding()}
            intent = None
            if intent_path.exists() or intent_path.is_symlink():
                intent = self._read('maintenance', operation_id, 'restore-intent')
                if intent.get('status') != 'restoring' or any(intent.get(key) != value for key, value in binding.items()):
                    raise ValueError('Restoration intent binding differs')
            elif outcome.exists() or outcome.is_symlink():
                raise ValueError('Restoration receipt has no intent')
            # Validate every retained copy and active destination before mutation.
            for item in operation['objects']:
                source = self._quarantine_path(operation_id, item['sha256'])
                destination = self.object_path(item['sha256'])
                if source.exists() or source.is_symlink():
                    if not source.is_file() or source.is_symlink() or source.stat().st_size != item['size_bytes'] or digest(source) != item['sha256']:
                        raise ValueError('Quarantine integrity failure')
                elif not destination.is_file():
                    raise ValueError('Quarantine recovery object is missing')
                if destination.exists() or destination.is_symlink():
                    if not destination.is_file() or destination.is_symlink() or destination.stat().st_size != item['size_bytes'] or digest(destination) != item['sha256']:
                        raise ValueError('Existing object integrity failure')
            if outcome.exists() or outcome.is_symlink():
                receipt = self._read('maintenance', operation_id, 'restored')
                if receipt.get('status') != 'restored' or receipt.get('restore_intent_sha256') != record_digest(intent):
                    raise ValueError('Restoration receipt binding differs')
                if any(not self._quarantine_path(operation_id, item['sha256']).is_file() for item in operation['objects']):
                    raise ValueError('Restoration retained copy is missing')
                if any(not self.object_path(item['sha256']).is_file() for item in operation['objects']):
                    raise ValueError('Restored object is missing')
                return receipt
            if intent is None:
                intent = self._record('maintenance', {'id': operation_id, 'status': 'restoring',
                    'actor': actor, 'reason': reason, **binding}, 'restore-intent')
            sync_directory(intent_path.parent)
            sync_directory(intent_path.parent.parent)
            for item in operation['objects']:
                source = self._quarantine_path(operation_id, item['sha256'])
                destination = self.object_path(item['sha256'])
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.link(destination, source)
                    sync_directory(source.parent)
                    sync_directory(source.parent.parent)
                if not destination.exists():
                    os.link(source, destination)
                sync_directory(destination.parent)
                sync_directory(destination.parent.parent)
            receipt = self._record('maintenance', {'id': operation_id, 'status': 'restored',
                'actor': actor, 'reason': reason, 'restore_intent_sha256': record_digest(intent)}, 'restored')
            sync_directory(outcome.parent)
            return receipt

    def _purge_state(self, operation_id, quarantine_days):
        from artifact_lifecycle import digest
        if isinstance(quarantine_days, bool) or not isinstance(quarantine_days, int) or quarantine_days < 0:
            raise ValueError('Quarantine days must be a nonnegative integer')
        operation = self._read('maintenance', operation_id)
        if operation.get('operation') != 'quarantine':
            raise ValueError('Operation is not a quarantine')
        restore = self._path('maintenance', operation_id, 'restore-intent')
        if restore.exists() or restore.is_symlink():
            raise ValueError('Quarantine restoration has started or was restored; create a new cleanup plan')
        if self._path('maintenance', operation_id, 'restored').exists():
            raise ValueError('Quarantine was restored; create a new cleanup plan')
        outcome = self._read('maintenance', operation_id, 'outcome')
        if outcome['status'] != 'quarantined':
            raise ValueError('Quarantine did not complete')
        if datetime.fromisoformat(outcome['created_at']) > datetime.now(timezone.utc) - timedelta(days=quarantine_days):
            raise ValueError('Quarantine retention has not expired')
        cleanup = self._read('maintenance', operation['plan_id'])
        if cleanup.get('artifact_policy') != self.artifact_policy:
            raise ValueError('Purge cleanup artifact policy differs')
        if cleanup['storage'] != self.paths.binding():
            raise ValueError('Purge storage binding changed')
        fingerprint, eligible = self._retention_state(cleanup['retention_days'],
            datetime.fromisoformat(cleanup['cutoff']), include_missing=True)
        eligible = {item['sha256']: item for item in eligible}
        intent = self._path('maintenance', operation_id, 'purge-intent').exists()
        from maintenance_observations import purge_checkpoint
        started_plan = self._read('maintenance', self._read('maintenance', operation_id, 'purge-intent')['plan_id']) if intent else None
        for index, item in enumerate(operation['objects']):
            if eligible.get(item['sha256']) != item:
                raise ValueError('Quarantine object is protected by current references')
            path = self._quarantine_path(operation_id, item['sha256'])
            if not path.exists():
                if intent:
                    purge_checkpoint(self, started_plan, index, required=True)
                    continue
                raise ValueError('Quarantine integrity failure: missing object')
            checkpoint = purge_checkpoint(self, started_plan, index) if intent else None
            if checkpoint is not None and checkpoint['file_identity'] != [path.stat().st_dev, path.stat().st_ino]:
                raise ValueError('Purge file checkpoint identity differs')
            if not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                raise ValueError('Quarantine integrity failure')
        return fingerprint, operation

    def plan_purge(self, operation_id, quarantine_days=None):
        if quarantine_days is None:
            quarantine_days = self.artifact_policy['quarantineDays']
        from artifact_lifecycle import identifier
        with self.transaction():
            if self._path('maintenance', operation_id, 'purge-intent').exists():
                raise ValueError('Purge already started; retry its original plan')
            fingerprint, operation = self._purge_state(operation_id, quarantine_days)
            return self._record('maintenance', {'id': identifier(), 'operation': 'purge-plan',
                'quarantine_id': operation_id, 'quarantine_days': quarantine_days,
                'artifact_policy': self.artifact_policy,
                'references_sha256': fingerprint, 'objects': operation['objects'],
                'storage': self.paths.binding(), 'purge_executed': False})

    def purge_cleanup(self, plan_id, actor, reason):
        from maintenance_observations import record_digest
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Purge requires actor and reason')
        with self.transaction():
            plan = self._read('maintenance', plan_id)
            if plan.get('artifact_policy') != self.artifact_policy:
                raise ValueError('Purge plan artifact policy differs')
            if plan.get('operation') != 'purge-plan' or plan['storage'] != self.paths.binding():
                raise ValueError('Invalid purge plan')
            operation_id = plan['quarantine_id']
            completed = self._path('maintenance', operation_id, 'purged')
            if completed.exists():
                result = self._read('maintenance', operation_id, 'purged')
                from maintenance_observations import completed_purge
                return completed_purge(self, plan)
            fingerprint, operation = self._purge_state(operation_id, plan['quarantine_days'])
            if fingerprint != plan['references_sha256'] or operation['objects'] != plan['objects']:
                raise ValueError('Purge plan is stale; create a new plan')
            intent = self._path('maintenance', operation_id, 'purge-intent')
            if intent.exists():
                existing = self._read('maintenance', operation_id, 'purge-intent')
                if existing.get('plan_id') != plan_id:
                    raise ValueError('Another purge plan owns this operation')
                if existing.get('plan_sha256') != record_digest(plan) or existing.get('operation_sha256') != record_digest(operation):
                    raise ValueError('Purge intent binding differs')
            else:
                self._record('maintenance', {'id': operation_id, 'plan_id': plan_id,
                    'actor': actor, 'reason': reason, 'plan_sha256': record_digest(plan),
                    'operation_sha256': record_digest(operation)}, 'purge-intent')
            from maintenance_observations import purge_checkpoint
            for index, item in enumerate(plan['objects']):
                path = self._quarantine_path(operation_id, item['sha256'])
                checkpoint = purge_checkpoint(self, plan, index)
                if checkpoint is None:
                    info = path.stat()
                    checkpoint = self._record('maintenance', {'id': operation_id,
                        'plan_id': plan_id, 'plan_sha256': record_digest(plan), 'object': item,
                        'path': str(path), 'file_identity': [info.st_dev, info.st_ino]}, f'purge-file-{index}')
                if path.exists() and checkpoint['file_identity'] != [path.stat().st_dev, path.stat().st_ino]:
                    raise ValueError('Purge file checkpoint identity differs')
                path.unlink(missing_ok=True)
            return self._record('maintenance', {'id': operation_id, 'plan_id': plan_id,
                'status': 'purged', 'actor': actor, 'reason': reason,
                'purge_intent_sha256': record_digest(self._read('maintenance', operation_id, 'purge-intent')),
                'bytes_removed': sum(item['size_bytes'] for item in plan['objects'])}, 'purged')
