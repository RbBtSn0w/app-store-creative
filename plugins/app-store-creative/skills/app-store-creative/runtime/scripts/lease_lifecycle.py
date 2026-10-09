"""Immutable lease generations and explicit recovery of expired executions."""
from datetime import datetime, timedelta, timezone
import hmac
from contextlib import contextmanager
import threading


def utcnow():
    return datetime.now(timezone.utc)


def duration(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 86400:
        raise ValueError('Lease seconds must be an integer from 1 through 86400')
    return seconds


class LeaseOperations:
    def _lease(self, attempt_id):
        directory = self.paths.workspace / 'records/attempt-leases' / attempt_id
        generations = [int(p.stem) for p in directory.glob('*.json')]
        if not generations:
            raise ValueError('Attempt has no execution lease')
        return self._read('attempt-leases', attempt_id, str(max(generations)))

    def _check_lease(self, attempt_id, lease_token=None):
        lease = self._lease(attempt_id)
        token = lease_token if lease_token is not None else self._owned_leases.get(attempt_id)
        if not isinstance(token, str) or not hmac.compare_digest(token, lease['lease_token']):
            raise ValueError('Execution lease token does not match')
        if datetime.fromisoformat(lease['expires_at']) <= utcnow():
            raise ValueError('Execution lease expired')
        return lease

    def _new_lease(self, attempt_id, owner, seconds, generation):
        from artifact_lifecycle import identifier
        lease = self._record('attempt-leases', {'id': attempt_id, 'owner': owner,
            'generation': generation, 'lease_token': identifier(),
            'expires_at': (utcnow() + timedelta(seconds=duration(seconds))).isoformat()}, str(generation))
        self._owned_leases[attempt_id] = lease['lease_token']
        return lease

    def _start_attempt_locked(self, run_id, stage, owner, retry_of, lease_seconds):
        from artifact_lifecycle import identifier
        identity = identifier()
        work = self.work_path(identity)
        lease = self._new_lease(identity, owner, lease_seconds, 1)
        data = self._record('attempts', {'id': identity, 'run_id': run_id,
            'stage': stage, 'owner': owner, 'retry_of': retry_of,
            'implementation': self._implementation_identity,
            'lease_expires_at': lease['expires_at']}, 'started')
        work.mkdir(parents=True)
        return {**data, 'lease_token': lease['lease_token'], 'work_path': str(work)}

    def renew_attempt(self, attempt_id, lease_token=None, lease_seconds=3600):
        duration(lease_seconds)
        with self.transaction():
            attempt = self._active_attempt(attempt_id, lease_token)
            previous = self._lease(attempt_id)
            return self._new_lease(attempt_id, attempt['owner'], lease_seconds, previous['generation'] + 1)

    def recover_attempt(self, attempt_id, owner, reason, lease_seconds=3600):
        duration(lease_seconds)
        if not isinstance(owner, str) or not owner.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('Recovery requires owner and reason')
        with self.transaction():
            attempt = self._read('attempts', attempt_id, 'started')
            self._run(attempt['run_id'])
            if self._path('attempts', attempt_id, 'outcome').exists():
                raise ValueError('Attempt has ended; start an explicit retry')
            lease = self._lease(attempt_id)
            if datetime.fromisoformat(lease['expires_at']) > utcnow():
                raise ValueError('Execution lease is still active')
            self._record('attempts', {'id': attempt_id, 'run_id': attempt['run_id'],
                'status': 'interrupted', 'reason': reason, 'recovered_by': owner,
                'expired_generation': lease['generation']}, 'outcome')
            return self._start_attempt_locked(attempt['run_id'], attempt['stage'], owner, attempt_id, lease_seconds)

    @contextmanager
    def keep_lease(self, attempt_id, lease_seconds=3600):
        """Keep a producer leased until it is ready to commit its outcome."""
        duration(lease_seconds)
        self.renew_attempt(attempt_id, lease_seconds=lease_seconds)
        stop = threading.Event()
        failures = []
        def heartbeat():
            while not stop.wait(max(0.1, lease_seconds / 3)):
                try:
                    self.renew_attempt(attempt_id, lease_seconds=lease_seconds)
                except Exception as error:
                    failures.append(error)
                    return
        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        try:
            yield
            if failures:
                raise ValueError('Production lease renewal failed') from failures[0]
        finally:
            stop.set()
            worker.join()
