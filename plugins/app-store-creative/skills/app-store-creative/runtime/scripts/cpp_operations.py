"""Reserve one external write at a time and reconcile its observed effect."""
import fcntl

from cpp_campaign import campaign_dir, inside, read
from cpp_delivery import handoff, status
from studio_contract import atomic_json


def observed_effect(operation, observation):
    kind, scope, desired = (operation[k] for k in ('kind', 'scope', 'desired'))
    if observation['status'] != 'observed':
        return False
    if kind == 'preparePage':
        return observation['name'] == desired['name']
    if kind == 'prepareVersion':
        return (observation['pageId'] == scope['page_id']
                and observation['pageVersionId'] not in desired['previousVersionIds']
                and observation['reviewState'] == 'PREPARE_FOR_SUBMISSION')
    if (scope['page_id'], scope['page_version_id']) != (observation['pageId'], observation['pageVersionId']):
        return False
    if kind == 'updateDeepLink':
        return observation['deepLink'] == desired
    if kind == 'prepareLocalization':
        return desired in observation['localizations']
    loc = observation['localizations'].get(scope['locale'])
    if not loc or loc['localizationId'] != scope['cpp_localization_id']:
        return False
    if kind == 'updateText':
        return loc['promotionalText'] == desired
    if kind == 'replaceKeywords':
        return sorted(loc['keywords']) == sorted(desired)
    if kind == 'reconcileMedia':
        return loc['media'].get(scope['target']) == [a['sha256'] for a in desired['after']]
    raise ValueError('Unknown CPP operation')


def transition(root, plan, observation_path, operation_id, action):
    base = campaign_dir(root, plan['campaignKey'])
    ledger = inside(root, base / 'operations.json')
    with inside(root, base / 'operations.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        records = read(ledger) if ledger.exists() else {}
        record = records.get(operation_id)
        if action == 'reconcile':
            if not record or record['planDigest'] != plan['planDigest']:
                raise ValueError('No matching claim to reconcile')
            if record['state'] == 'verified':
                return dict(status='verified', operationId=operation_id)
            brief = read(inside(root, plan['sources'][0]))
            observed = status(root, plan['campaignKey'], brief, observation_path)
            if (observed.get('planDigest') != plan['planDigest']
                    or not observed_effect(record['operation'], observed)):
                return dict(status='blocked', reasonCode='outcomeUnknown', operationId=operation_id)
            record.update(state='verified', evidenceSha256=observed['evidenceSha256'])
            atomic_json(ledger, records)
            return dict(status='verified', operationId=operation_id)
        if record and record['state'] == 'verified':
            current = handoff(root, plan, observation_path)
            if any(op['operationId'] == operation_id for op in current['operations']):
                return dict(status='blocked', reasonCode='remoteDrift', operationId=operation_id)
            return dict(status='verified', operationId=operation_id)
        if any(rec['state'] == 'reserved' for rec in records.values()):
            return dict(status='blocked', reasonCode='reconcileOutstandingClaim',
                        outstanding=[k for k, v in records.items() if v['state'] == 'reserved'])
        current = handoff(root, plan, observation_path)
        op = next((op for op in current['operations'] if op['operationId'] == operation_id), None)
        if op is None:
            raise ValueError('Operation is outside the current handoff')
        records[operation_id] = dict(planDigest=plan['planDigest'], operation=op, state='reserved')
        atomic_json(ledger, records)
        return dict(status='reserved', operation=op, remoteWrite=False)
