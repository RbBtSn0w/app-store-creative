"""Scoped logical payload budget for verified retained sealed revisions."""
import json
from operation_history import read_lock
from delivery_lifecycle import relative_name
from artifact_policy import resolve


def inspect(core, candidate_id=None):
    core._assert_paths()
    policy = resolve(core._live_configuration())
    limit = policy['mediaBudgetBytes']
    report = {'schema_version': 1, 'status': 'UNKNOWN', 'configured_limit_bytes': limit,
              'current_payload_bytes': None, 'observed_payload_bytes': 0,
              'candidate_id': candidate_id, 'candidate_payload_bytes': None,
              'forecast_payload_bytes': None, 'unverified_deliveries': [],
              'git_history_bytes': None, 'remote_storage_bytes': None, 'writes_performed': False,
              'scope': 'Logical artifact payload copies in registered retained local revisions; excludes metadata and unobserved Git/remote history'}
    lock = core.paths.workspace / 'write.lock'
    if not lock.exists() and not lock.is_symlink():
        report['reason'] = 'Workspace read lock is unavailable; no state created'
        return report
    with read_lock(core):
        policy = resolve(core._live_configuration())
        if policy['mediaBudgetBytes'] != limit:
            raise ValueError('Budget policy changed during inspection')
        for path in sorted((core.paths.workspace / 'records/deliveries').glob('*.json')):
            try:
                delivery = core._read('deliveries', path.stem)
                package = core.delivery_path(delivery)
                from delivery_lifecycle import verify_archive
                verify_archive(package, delivery['manifest_sha256'])
                graph = json.loads((package / 'evidence/provenance.json').read_text())
                payloads = {item['path']: item['size_bytes'] for item in graph['nodes']}
                report['observed_payload_bytes'] += sum(payloads.values())
            except (ValueError, OSError, KeyError, TypeError) as error:
                report['unverified_deliveries'].append({'id': path.stem, 'reason': str(error)})
        if candidate_id is not None:
            candidate, _ = core._candidate(candidate_id)
            closure = core._closure(candidate['artifacts'])
            payloads = {}
            for identity, item in closure.items():
                prefix = ('media/' if identity in candidate['artifacts'] else
                          'evidence/render/' if item['role'] == 'render-evidence' else 'recipe/inputs/')
                path = prefix + relative_name(item['logical_path'])
                payload = (item['sha256'], item['size_bytes'])
                if path in payloads and payloads[path] != payload:
                    raise ValueError('Candidate budget has conflicting payload paths')
                payloads[path] = payload
            report['candidate_payload_bytes'] = sum(size for _, size in payloads.values())
        if report['unverified_deliveries']:
            return report
        report['current_payload_bytes'] = report['observed_payload_bytes']
        report['forecast_payload_bytes'] = report['current_payload_bytes'] + (report['candidate_payload_bytes'] or 0)
        report['status'] = ('NOT_CONFIGURED' if limit is None else
                            'OVER_BUDGET' if report['forecast_payload_bytes'] > limit else 'WITHIN_BUDGET')
    return report
