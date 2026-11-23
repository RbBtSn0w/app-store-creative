"""Pre-export review of screenshot recipes against a sealed release."""
from dataclasses import dataclass
from pathlib import PurePosixPath

from record_primitives import digest
from studio_contract import check_config, local_asset, resolve_card


@dataclass
class Placement:
    position: int
    copy: dict
    design: dict
    sources: dict
    issues: list


def placements(config, source_hash):
    project = config['project']
    result = {}
    for language in project.get('locales', ['en-US']):
        for target in config.get('targets', ['iphone_6_9']):
            for position, card in enumerate(config['cards'], 1):
                data, localized = resolve_card(config, card, target, language)
                issues = []
                design = {key: value for key, value in data.items()
                          if key not in ('variants', 'headline', 'subheadline', 'screenshot')}
                design['theme'] = config.get('theme', {})
                design['connectedTrack'] = config.get('connectedTrack', False)
                if design['connectedTrack']:
                    design['trackLength'] = len(config['cards'])
                sources = {}
                uses_capture = data.get('layout') != 'pure_text'
                if uses_capture:
                    sources['Capture'] = data.get('screenshot')
                bg = data.get('customBackground', design['theme'].get('background', {}))
                if bg.get('type') == 'image':
                    sources['Background'] = bg.get('imageUrl')
                for label, name in sources.items():
                    try:
                        fingerprint = source_hash(name) if name else None
                    except (ValueError, OSError):
                        fingerprint = None
                    sources[label] = fingerprint
                    if fingerprint is None:
                        issues.append(label + ' unavailable')
                if language != project.get('defaultLocale', 'en-US') and not localized.get('inheritDefault'):
                    if not localized.get('headline') or (uses_capture and not localized.get('screenshot')):
                        issues.append('Review inherited copy or capture')
                path = f"{language}/{target}/{card['id']}.png"
                result[path] = Placement(position, {key: data.get(key) for key in ('headline', 'subheadline')},
                                         design, sources, issues)
    return result


def screenshot_plan(core, baseline_id):
    import json
    delivery = core._read('deliveries', baseline_id)
    config = check_config(core.config)
    from studio_contract import release_platform
    platform = release_platform(config)
    if (delivery['project_id'] != config['project']['id']
            or delivery['target']['platform'].upper() != platform.upper()):
        raise ValueError('Choose a baseline from the same project and platform')
    package = core.delivery_path(delivery)
    previous = json.loads((package / 'evidence/reviewed-config.json').read_text())
    manifest = json.loads((package / 'manifest.json').read_text())
    hashes = {entry['path'].removeprefix('recipe/inputs/'): entry['sha256'] for entry in manifest['recipe_inputs']}
    before = placements(previous, lambda name: hashes.get(str(PurePosixPath(name.lstrip('/')))))
    cache = {}

    def current_hash(name):
        if name not in cache:
            cache[name] = digest(local_asset(core.paths.project, name, config))
        return cache[name]

    after = placements(config, current_hash)
    rows = []
    for path in sorted(before.keys() | after.keys()):
        old, new = before.get(path), after.get(path)
        reasons = list(new.issues) if new else []
        copy_changes = []
        if not old:
            reasons.append('New placement')
        elif not new:
            reasons.append('Removed placement')
        else:
            if old.position != new.position:
                reasons.append(f'Position {old.position} → {new.position}')
            if old.copy != new.copy:
                reasons.append('Localized copy changed')
                copy_changes = [{'field': key, 'before': old.copy[key], 'after': new.copy[key]}
                                for key in old.copy if old.copy[key] != new.copy[key]]
            if old.design != new.design:
                reasons.append('Composition changed')
            for label in sorted(old.sources.keys() | new.sources.keys()):
                if old.sources.get(label) != new.sources.get(label):
                    reasons.append(label + ' changed')
        rows.append({'path': path, 'present': new is not None, 'reasons': reasons, 'copy_changes': copy_changes})
    return {'baseline_id': baseline_id, 'assets': rows}


def check_capture_copy(core, locale, target, card_id, phrase):
    import json
    from pathlib import Path
    import subprocess
    if not isinstance(phrase, str) or not 1 <= len(phrase.strip()) <= 160:
        raise ValueError('Enter a phrase of 1–160 characters to locate in the capture')
    config = check_config(core.config)
    if locale not in config['project'].get('locales', ['en-US']) or target not in config.get('targets', ['iphone_6_9']):
        raise ValueError('Choose a configured language and target')
    card = next((card for card in config['cards'] if card['id'] == card_id), None)
    if not card:
        raise ValueError('Choose an existing screenshot card')
    resolved, _ = resolve_card(config, card, target, locale)
    if resolved.get('layout') == 'pure_text':
        raise ValueError('This card contains only text')
    path = local_asset(core.paths.project, resolved.get('screenshot'), config)
    fingerprint = digest(path)
    try:
        scan = subprocess.run(['/usr/bin/swift', str(Path(__file__).with_name('capture_copy.swift')),
                               str(path), phrase.strip()], text=True, capture_output=True, timeout=90)
    except subprocess.TimeoutExpired as error:
        raise ValueError('Local text recognition timed out') from error
    if scan.returncode:
        raise ValueError('Local text recognition unavailable: ' + scan.stderr.strip()[-400:])
    if digest(path) != fingerprint:
        raise ValueError('Capture changed during text recognition')
    return {'capture_sha256': fingerprint, 'phrase': phrase.strip(), 'matches': json.loads(scan.stdout)}
