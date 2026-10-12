"""Reference-aware retention with reversible, journaled object quarantine."""
from datetime import datetime, timedelta, timezone
import hashlib
import os


class RetentionOperations:
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
        paths = sorted(p for p in records.rglob('*.json') if 'maintenance' not in p.relative_to(records).parts)
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
        for identity, artifact in artifacts.items():
            outcome = self._path('attempts', artifact['attempt_id'], 'outcome')
            if not outcome.exists():
                protected.add(identity)
            elif datetime.fromisoformat(self._read('attempts', artifact['attempt_id'], 'outcome')['created_at']) > cutoff:
                protected.add(identity)
        pending = list(protected)
        while pending:
            identity = pending.pop()
            if identity not in artifacts:
                raise ValueError('Missing referenced artifact')
            for dependency in artifacts[identity].get('inputs', []):
                if dependency not in protected:
                    protected.add(dependency); pending.append(dependency)
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

    def plan_cleanup(self, retention_days=30):
        from artifact_lifecycle import identifier
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 0:
            raise ValueError('Retention days must be a nonnegative integer')
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        with self.transaction():
            fingerprint, objects = self._retention_state(retention_days, cutoff)
            return self._record('maintenance', {'id': identifier(), 'operation': 'cleanup-plan',
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
        if not actor or not reason:
            raise ValueError('Maintenance requires actor and reason')
        with self.transaction():
            plan = self._read('maintenance', plan_id)
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
        if not actor or not reason:
            raise ValueError('Maintenance requires actor and reason')
        with self.transaction():
            operation = self._read('maintenance', operation_id)
            if operation.get('operation') != 'quarantine':
                raise ValueError('Operation is not a quarantine')
            if self._path('maintenance', operation_id, 'purge-intent').exists():
                raise ValueError('Quarantine purge has started; recovery is unavailable')
            # Check the entire recovery set before restoring any object.
            for item in operation['objects']:
                source = self._quarantine_path(operation_id, item['sha256'])
                destination = self.object_path(item['sha256'])
                if source.exists():
                    if not source.is_file() or source.stat().st_size != item['size_bytes'] or digest(source) != item['sha256']:
                        raise ValueError('Quarantine integrity failure')
                elif not destination.is_file():
                    raise ValueError('Quarantine recovery object is missing')
                if destination.exists() and (destination.stat().st_size != item['size_bytes'] or digest(destination) != item['sha256']):
                    raise ValueError('Existing object integrity failure')
            for item in operation['objects']:
                source = self._quarantine_path(operation_id, item['sha256'])
                destination = self.object_path(item['sha256'])
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.exists():
                    os.link(source, destination)
            # Quarantine copies remain available for crash-safe and idempotent recovery.
            outcome = self._path('maintenance', operation_id, 'restored')
            if outcome.exists():
                return self._read('maintenance', operation_id, 'restored')
            return self._record('maintenance', {'id': operation_id, 'status': 'restored',
                'actor': actor, 'reason': reason}, 'restored')

    def _purge_state(self, operation_id, quarantine_days):
        from artifact_lifecycle import digest
        if isinstance(quarantine_days, bool) or not isinstance(quarantine_days, int) or quarantine_days < 0:
            raise ValueError('Quarantine days must be a nonnegative integer')
        operation = self._read('maintenance', operation_id)
        if operation.get('operation') != 'quarantine':
            raise ValueError('Operation is not a quarantine')
        if self._path('maintenance', operation_id, 'restored').exists():
            raise ValueError('Quarantine was restored; create a new cleanup plan')
        outcome = self._read('maintenance', operation_id, 'outcome')
        if outcome['status'] != 'quarantined':
            raise ValueError('Quarantine did not complete')
        if datetime.fromisoformat(outcome['created_at']) > datetime.now(timezone.utc) - timedelta(days=quarantine_days):
            raise ValueError('Quarantine retention has not expired')
        cleanup = self._read('maintenance', operation['plan_id'])
        if cleanup['storage'] != self.paths.binding():
            raise ValueError('Purge storage binding changed')
        fingerprint, eligible = self._retention_state(cleanup['retention_days'],
            datetime.fromisoformat(cleanup['cutoff']), include_missing=True)
        eligible = {item['sha256']: item for item in eligible}
        intent = self._path('maintenance', operation_id, 'purge-intent').exists()
        for item in operation['objects']:
            if eligible.get(item['sha256']) != item:
                raise ValueError('Quarantine object is protected by current references')
            path = self._quarantine_path(operation_id, item['sha256'])
            if not path.exists():
                if intent:
                    continue
                raise ValueError('Quarantine integrity failure: missing object')
            if not path.is_file() or path.stat().st_size != item['size_bytes'] or digest(path) != item['sha256']:
                raise ValueError('Quarantine integrity failure')
        return fingerprint, operation

    def plan_purge(self, operation_id, quarantine_days=7):
        from artifact_lifecycle import identifier
        with self.transaction():
            if self._path('maintenance', operation_id, 'purge-intent').exists():
                raise ValueError('Purge already started; retry its original plan')
            fingerprint, operation = self._purge_state(operation_id, quarantine_days)
            return self._record('maintenance', {'id': identifier(), 'operation': 'purge-plan',
                'quarantine_id': operation_id, 'quarantine_days': quarantine_days,
                'references_sha256': fingerprint, 'objects': operation['objects'],
                'storage': self.paths.binding(), 'purge_executed': False})

    def purge_cleanup(self, plan_id, actor, reason):
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Purge requires actor and reason')
        with self.transaction():
            plan = self._read('maintenance', plan_id)
            if plan.get('operation') != 'purge-plan' or plan['storage'] != self.paths.binding():
                raise ValueError('Invalid purge plan')
            operation_id = plan['quarantine_id']
            completed = self._path('maintenance', operation_id, 'purged')
            if completed.exists():
                result = self._read('maintenance', operation_id, 'purged')
                if result['plan_id'] != plan_id:
                    raise ValueError('Quarantine was purged by another plan')
                return result
            fingerprint, operation = self._purge_state(operation_id, plan['quarantine_days'])
            if fingerprint != plan['references_sha256'] or operation['objects'] != plan['objects']:
                raise ValueError('Purge plan is stale; create a new plan')
            intent = self._path('maintenance', operation_id, 'purge-intent')
            if intent.exists():
                if self._read('maintenance', operation_id, 'purge-intent')['plan_id'] != plan_id:
                    raise ValueError('Another purge plan owns this operation')
            else:
                self._record('maintenance', {'id': operation_id, 'plan_id': plan_id,
                    'actor': actor, 'reason': reason}, 'purge-intent')
            for item in plan['objects']:
                self._quarantine_path(operation_id, item['sha256']).unlink(missing_ok=True)
            return self._record('maintenance', {'id': operation_id, 'plan_id': plan_id,
                'status': 'purged', 'actor': actor, 'reason': reason,
                'bytes_removed': sum(item['size_bytes'] for item in plan['objects'])}, 'purged')
