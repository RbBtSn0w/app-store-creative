"""Local, reproducible PPO observations and decisions for screenshot experiments."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from delivery_lifecycle import verify_archive
from record_primitives import canonical, digest
from storage_paths import StoragePaths


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f'Duplicate PPO field: {key}')
        fields[key] = value
    return fields


def read(path):
    value = json.loads(path.read_bytes(), object_pairs_hook=unique_fields)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path.name}")
    return value


def write_once(path, value):
    """Publish a complete record and allow identical retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent) as tmp:
        tmp.write(canonical(value) + b'\n')
        tmp.flush()
        try:
            os.link(tmp.name, path)
        except FileExistsError:
            if path.is_symlink() or canonical(read(path)) != canonical(value):
                raise ValueError(f"Conflicting existing record: {path.name}")
    return value


def number(value, field, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected a number for {field}")
    result = Decimal(str(value))
    if not result.is_finite() or (low is not None and result < low) or (high is not None and result > high):
        raise ValueError(f"Out of range: {field}")
    return result


def component(value):
    if (not isinstance(value, str) or not value.strip() or value in ('.', '..') or '/' in value
            or '\\' in value or any(ord(c) < 32 for c in value) or value.startswith('<')):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def preflight(config, experiment):
    policy = experiment['policy']
    if not isinstance(policy, dict):
        raise ValueError('policy must be an object')
    for key, available in [('locales', config['project'].get('locales', ['en-US'])),
                           ('targets', config.get('targets', ['iphone_6_9']))]:
        items = policy.get(key)
        if (not isinstance(items, list) or not items or any(component(item) not in available for item in items)
                or len(set(items)) != len(items)):
            raise ValueError(f"policy.{key} must be a nonempty unique subset of the project")
    from export_engine import TARGET_SPECS
    if any(item not in TARGET_SPECS or not item.startswith(('iphone_', 'ipad_')) for item in policy['targets']):
        raise ValueError('PPO screenshot policy requires iPhone or iPad targets')
    if not isinstance(policy.get('testedChange'), str) or not policy['testedChange'].strip():
        raise ValueError('Provide policy.testedChange')
    threshold = policy.get('minRelativeLiftPct')
    if threshold is not None:
        number(threshold, 'minRelativeLiftPct', 0)
    days = policy.get('durationEstimateDays')
    if days is not None:
        source = policy.get('estimateSource')
        if type(days) is not int or days < 1 or not isinstance(source, str) or not source.strip():
            raise ValueError('Provide positive durationEstimateDays and estimateSource')
    active = policy.get('anotherTestRunning', False)
    if type(active) is not bool:
        raise ValueError('anotherTestRunning must be boolean')
    traffic = experiment['trafficProportion']
    reasons = []
    if active or (days is not None and days > 90):
        reasons.append('active-test' if active else 'estimate-over-90-days')
        status = 'defer'
    else:
        if days is None:
            reasons.append('unknown-duration')
        if threshold is None:
            reasons.append('missing-threshold')
        if traffic == 100:
            reasons.append('no-original-traffic')
        status = 'needs-input' if reasons else 'ready'
    return {'status': status, 'reasons': reasons, 'control_pct': 100 - traffic,
            'per_treatment_pct': traffic / len(experiment['treatments'])}


def recipe_digest(config):
    # Production can inherit theme, cards and assets from the project.
    return checksum({k: v for k, v in config.items() if k not in ('storage', 'experiments')})


def composition_digest(config, policy):
    from studio_contract import resolve_card
    # Compare effective localized compositions even for archives produced for a subset of devices.
    cells = {locale: {target: [resolve_card(config, card, target, locale)[0] for card in config['cards']]
                      for target in policy['targets']} for locale in policy['locales']}
    return checksum({'theme': config.get('theme', {}), 'cells': cells, 'studio': config.get('studio', {})})


def deployed_assets(root, config, handoff, group):
    order = group['card_order']
    project = handoff['project']
    releases = StoragePaths.resolve(root, config).releases
    package = releases.joinpath(*(component(project[key]) for key in ('id', 'platform', 'version')),
                                component(group['delivery_id']))
    if not package.resolve().is_relative_to(releases):
        raise ValueError('Delivery escapes release root')
    verify_archive(package, group['manifest_sha256'])
    manifest = read(package / 'manifest.json')
    target_identity = {key: project[key] for key in ('platform', 'version')}
    if (manifest['project_id'] != project['id'] or manifest['revision_id'] != group['delivery_id']
            or any(manifest['target'].get(key) != value for key, value in target_identity.items())):
        raise ValueError('Delivery identity mismatch')
    declared = {row['path']: row['sha256'] for row in manifest['assets'] if row['role'] == 'screenshot'}
    reviewed = read(package / 'evidence/reviewed-config.json')
    if [card['id'] for card in reviewed['cards']] != order:
        raise ValueError('Reviewed delivery card order differs from the handoff')
    assets = {}
    policy = handoff['policy']
    if composition_digest(reviewed, policy) != group['composition_sha256']:
        raise ValueError('Reviewed delivery differs from the planned composition')
    for locale in policy['locales']:
        for target in policy['targets']:
            prefix = f'{component(locale)}/{component(target)}/'
            expected = [prefix + component(card) + '.png' for card in order]
            scoped = {path.removeprefix('media/') for path in declared if path.startswith('media/' + prefix)}
            if scoped != set(expected):
                raise ValueError(f'Screenshot set differs from measured scope: {prefix}')
            # verify_archive already compared every declared hash to the file's raw bytes.
            assets.update((name, declared['media/' + name]) for name in expected)
    return assets


def bind(root, config, handoff_path, app_id, experiment_id, treatment_ids):
    h = read(handoff_path)
    if (h.get('schema_version') != 1 or h.get('generated_by') != 'app-store-creative:ppo-engine' or h['project']['id'] != config['project']['id']
            or h['project']['platform'] != 'IOS' or not app_id.isascii() or not app_id.isdigit()
            or (h['project'].get('app_id') and str(h['project']['app_id']) != app_id) or not h.get('policy')):
        raise ValueError('Expected a measured iOS handoff for this project and app')
    component(experiment_id)
    groups = h['treatments']
    if ({g['id'] for g in groups} != set(treatment_ids) or len(groups) != len(treatment_ids)
            or len(set(treatment_ids.values())) != len(groups) or 'original' in treatment_ids.values()):
        raise ValueError('Provide a unique remote ID for every treatment')
    if any(not group.get('manifest_sha256') for group in [h['control'], *groups]):
        raise ValueError('Handoff is a draft. Supply sealed deliveries before binding')
    assets = {'original': deployed_assets(root, config, h, h['control'])}
    for group in groups:
        tid = group['id']
        remote = component(treatment_ids[tid])
        if group.get('app_icon_name'):
            raise ValueError('Measured screenshot workflow does not support alternate icons')
        assets[remote] = deployed_assets(root, config, h, group)
        if group['reorder_only'] and assets[remote] != assets['original']:
            raise ValueError(f'Screenshot content changed during reorder: {tid}')
    return {'schema_version': 1, 'generated_by': 'app-store-creative:ppo-binding', 'project_id': h['project']['id'],
            'handoff_sha256': digest(handoff_path), 'app_id': app_id, 'experiment_id': experiment_id,
            'treatments': treatment_ids, 'assets': assets}


def decide(rows, ended, threshold):
    states = {'Performing Better', 'Performing Worse', 'Collecting Data', 'Likely to be Inconclusive'}
    winners = []
    unresolved = threshold is None
    for row in rows:
        status = row['apple_status']
        lift = row.get('relative_lift_pct')
        confidence = row.get('confidence_pct')
        if status not in states:
            return 'needs-review', 'unknown-status', None
        if status in ('Collecting Data', 'Likely to be Inconclusive'):
            unresolved = True
            continue
        if None in (lift, confidence, row.get('conversion_rate_pct')) or not row['unique_impressions']:
            unresolved = True
            continue
        if confidence < 90 or (status == 'Performing Better' and lift <= 0) or (status == 'Performing Worse' and lift >= 0):
            return 'needs-review', 'conflicting-apple-metrics', None
        if threshold is not None and status == 'Performing Better' and Decimal(str(lift)) >= Decimal(str(threshold)):
            winners.append(row['treatment_id'])
    statuses = {row['apple_status'] for row in rows}
    if not ended:
        reason = 'likely-inconclusive' if 'Likely to be Inconclusive' in statuses else 'test-running'
        return 'wait', reason, None
    if unresolved:
        reason = 'missing-preregistered-threshold' if threshold is None else 'insufficient-evidence'
        return 'inconclusive', reason, None
    if len(winners) > 1:
        return 'needs-review', 'multiple-qualified-treatments', None
    if winners:
        return 'use-treatment', 'qualified-treatment', winners[0]
    reason = 'all-treatments-worse' if statuses == {'Performing Worse'} else 'below-business-threshold'
    return 'keep-control', reason, None


def assess(root, config, handoff, binding, snapshot):
    paths = {'handoff': handoff, 'binding': binding, 'snapshot': snapshot}
    refs = {key: {'path': os.path.relpath(path, root), 'sha256': digest(path)} for key, path in paths.items()}
    b = read(binding)
    verified = bind(root, config, handoff, b['app_id'], b['experiment_id'], b['treatments'])
    if canonical(verified) != canonical(b):
        raise ValueError('Binding differs from deployed assets or handoff')
    h, s = read(handoff), read(snapshot)
    policy = h['policy']
    scope = {k: policy[k] for k in ('locales', 'targets')}
    if (type(s.get('schema_version')) is not int or s['schema_version'] != 1 or
            s['binding_sha256'] != digest(binding) or s['experiment_id'] != b['experiment_id']
            or s['app_id'] != b['app_id'] or s['scope'] != scope):
        raise ValueError('Snapshot binding, scope or experiment mismatch')
    source = (root / s['source']).resolve()
    if digest(source) != s['source_sha256']:
        raise ValueError('Snapshot source checksum mismatch')
    if datetime.fromisoformat(s['observed_at']).utcoffset() is None or s['state'] not in ('running', 'ended'):
        raise ValueError('Provide a timezone-aware observation time and experiment state')
    rows = s['rows']
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Expected snapshot rows')
    by_id = {row['treatment_id']: row for row in rows}
    if set(by_id) != set(b['assets']) or len(rows) != len(by_id):
        raise ValueError('Duplicate, missing or unmapped treatment row')
    for row in rows:
        n = row['unique_impressions']
        if n is not None and (type(n) is not int or n < 0):
            raise ValueError('Invalid unique_impressions')
        for key, low, high in [('conversion_rate_pct', 0, 100), ('relative_lift_pct', -100, None), ('confidence_pct', 0, 100)]:
            if row.get(key) is not None:
                number(row[key], key, low, high)
    if by_id['original'].get('apple_status') != 'Original':
        action, reason, remote = 'needs-review', 'original-row-mismatch', None
    elif s['baseline'] != 'original' or h['experiment']['traffic_proportion'] == 100:
        action, reason, remote = 'needs-review', 'original-baseline-unavailable', None
    else:
        action, reason, remote = decide([by_id[r] for r in b['treatments'].values()],
                                        s['state'] == 'ended', policy.get('minRelativeLiftPct'))
        if action in ('use-treatment', 'keep-control') and (not by_id['original']['unique_impressions'] or
                                                            by_id['original'].get('conversion_rate_pct') is None):
            action, reason, remote = 'inconclusive', 'missing-control-data', None
    if any(digest(path) != refs[key]['sha256'] for key, path in paths.items()):
        raise ValueError('PPO inputs changed during assessment')
    chosen = next((k for k, v in b['treatments'].items() if v == remote), None)
    return {'schema_version': 1, 'generated_by': 'app-store-creative:ppo-assessment', 'rule_version': 1,
            'project_id': b['project_id'], 'experiment_id': h['experiment']['id'], 'observed_at': s['observed_at'],
            'scope': scope, 'refs': refs, 'action': action, 'reason': reason, 'rows': rows,
            'baseline': s['baseline'], 'state': s['state'], 'threshold_pct': policy.get('minRelativeLiftPct'),
            'source': {'path': s['source'], 'sha256': s['source_sha256']}, 'selected_treatment': chosen}


def assessed_result(root, config, handoff, assessment_path):
    a = read(assessment_path)
    refs = a['refs']
    replay = assess(root, config, handoff, root / refs['binding']['path'], root / refs['snapshot']['path'])
    if canonical(a) != canonical(replay) or a['action'] not in ('use-treatment', 'keep-control', 'inconclusive'):
        raise ValueError('A matching terminal assessment is required')
    h = read(handoff)
    chosen = next((row for row in h['treatments'] if row['id'] == a['selected_treatment']), {})
    selected = h['control']['delivery_id'] if a['action'] == 'keep-control' else chosen.get('delivery_id')
    return {'schema_version': 2, 'generated_by': 'app-store-creative:ppo-result', 'project': h['project'],
            'experiment': h['experiment'], 'market': ', '.join(a['scope']['locales']), 'tested_change': h['policy']['testedChange'],
            'observation': a['reason'], 'evidence_reference': os.path.relpath(assessment_path, root),
            'assessment_sha256': digest(assessment_path), 'handoff_sha256': refs['handoff']['sha256'],
            'measured_scope': a['scope'], 'decision': a['action'], 'selected_treatment': a['selected_treatment'],
            'selected_delivery': selected, 'control_delivery': h['control']['delivery_id'],
            'treatment_deliveries': {g['id']: g['delivery_id'] for g in h['treatments']},
            'treatment_definition_sha256': chosen.get('definition_sha256')}


def replay_selection(root, config, result):
    path = root / result['evidence_reference']
    refs = read(path)['refs']
    if canonical(result) != canonical(assessed_result(root, config, root / refs['handoff']['path'], path)):
        raise ValueError('Result differs from replayed assessment')
    h = read(root / refs['handoff']['path'])
    tid = result['selected_treatment']
    if recipe_digest(config) != h['recipe_sha256'] or checksum(config['experiments'][h['experiment']['id']]) != h['experiment_sha256']:
        raise ValueError('Current recipe or experiment differs from the measured handoff')
    from ppo_experiment import derive_treatment_config
    from studio_contract import input_hashes
    derived = derive_treatment_config(config, h['experiment']['id'], tid)
    derived['storage'] = config.get('storage', {})
    sources, errors = input_hashes(root, derived, **result['measured_scope'])
    group = next(g for g in h['treatments'] if g['id'] == tid)
    project = h['project']
    package = StoragePaths.resolve(root, config).releases.joinpath(project['id'], project['platform'],
                                                                    project['version'], group['delivery_id'])
    archived = {row['path'].removeprefix('recipe/inputs/'): row['sha256']
                for row in read(package / 'manifest.json')['recipe_inputs']}
    changed = [name for name, sha in sources.items() if archived.get(name) != sha]
    if errors or changed:
        raise ValueError('Current screenshot inputs differ from measured delivery: ' + ', '.join(errors + changed))
    binding = read(root / refs['binding']['path'])
    return binding['assets'][binding['treatments'][result['selected_treatment']]]


def reproduction_project(root, config, result, derived, execute):
    """Use a stable project and sealed inputs so repeated runs retain the same authority."""
    from delivery_lifecycle import portable_recipe, relative_name
    import shutil
    project = result['project']
    paths = StoragePaths.resolve(root, config)
    archive = paths.releases.joinpath(project['id'], project['platform'], project['version'], result['selected_delivery'])
    manifest = read(archive / 'manifest.json')
    archived = {row['path'].removeprefix('recipe/inputs/'): row for row in manifest['recipe_inputs']}
    recipe = portable_recipe(derived, set(archived))
    scope = result['measured_scope']
    recipe.pop('experiments', None)
    recipe.pop('previewVideo', None)
    for localization in recipe.get('localizations', {}).values():
        localization.pop('previewVideo', None)
    recipe['targets'] = scope['targets']
    recipe['project']['locales'] = scope['locales']
    if recipe['project'].get('defaultLocale', 'en-US') not in scope['locales']:
        recipe['project']['defaultLocale'] = scope['locales'][0]
    recipe['storage'] = {'releaseRoot': str(paths.releases), 'publicationRoot': str(paths.publications)}
    project_root = StoragePaths.resolve(root, derived).workspace / 'ppo-reproductions' / checksum(result)
    cfg = project_root / 'creative.config.json'
    if project_root.resolve() != project_root:
        raise ValueError('Symlinked reproduction project')
    if execute:
        for name, row in archived.items():
            dest = project_root / 'inputs' / relative_name(name)
            if dest.resolve() != dest:
                raise ValueError('Symlinked reproduction input')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                with tempfile.NamedTemporaryFile(dir=dest.parent) as tmp:
                    with (archive / row['path']).open('rb') as src:
                        shutil.copyfileobj(src, tmp)
                    tmp.flush()
                    if digest(tmp.name) != row['sha256']:
                        raise ValueError(f'Archived input changed: {name}')
                    try:
                        os.link(tmp.name, dest)
                    except FileExistsError:
                        pass
            if dest.is_symlink() or digest(dest) != row['sha256']:
                raise ValueError(f'Reproduction input differs: {name}')
        write_once(cfg, recipe)
    return project_root, cfg
