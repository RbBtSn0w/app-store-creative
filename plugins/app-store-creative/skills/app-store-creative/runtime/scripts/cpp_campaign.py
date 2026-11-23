"""Compile evidence-backed custom product pages and reconcile local ASC snapshots."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from export_engine import TARGET_SPECS
from record_primitives import canonical
from studio_contract import inspect_png


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def inside(root, path):
    path = (root / path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path outside project')
    return path


def campaign_dir(root, key):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
        raise ValueError('Invalid campaign key')
    return inside(root, Path('.creative/cpp') / key)


def read(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected an object in {path.name}')
    return value


def required(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Missing or invalid {key}')
    return value


def strings(value, label, *, empty=False):
    if (not isinstance(value, list) or (not value and not empty)
            or any(not isinstance(v, str) or not v.strip() for v in value)
            or len(value) != len(set(value))):
        raise ValueError(f'Expected unique strings in {label}')
    return value


def verified(root, ref):
    path = inside(root, required(ref, 'path'))
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != required(ref, 'sha256'):
        raise ValueError(f'Changed input: {ref["path"]}')
    return path


def checked_url(page, app_id):
    value = page.get('url', '')
    parsed = urlsplit(value)
    if (parsed.scheme == 'https' and parsed.netloc == 'apps.apple.com'
            and parsed.path.rstrip('/').endswith('/id' + app_id)
            and parse_qs(parsed.query).get('ppid') == [page.get('pageId')]):
        return value
    return None


def inputs(root, key, proposal=None, inventory=None):
    base = campaign_dir(root, key)
    paths = [inside(root, p) for p in
             (base / 'brief.json', proposal or base / 'proposal.json', inventory or base / 'inventory.json')]
    return [read(p) for p in paths], [p.relative_to(root).as_posix() for p in paths]


def compile_plan(root, key, proposal=None, inventory=None):
    (brief, draft, stock), sources = inputs(root, key, proposal, inventory)
    if any(type(v.get('schemaVersion')) is not int or v['schemaVersion'] != 1 for v in (brief, draft, stock)):
        raise ValueError('Expected CPP schemaVersion 1')
    if brief.get('campaignKey') != key or required(brief, 'platform').upper() != 'IOS':
        raise ValueError('Campaign or platform mismatch')
    for field in ('appId', 'bundleId'):
        if required(brief, field) != required(stock, field):
            raise ValueError('Inventory belongs to another app')
    config = root / 'creative.config.json'
    if config.is_file() and read(config).get('project', {}).get('bundleId') != brief['bundleId']:
        raise ValueError('Project bundle does not match campaign')
    for field in ('audience', 'channel', 'intent'):
        required(brief, field)
    locales = strings(brief['locales'], 'locales')
    targets = strings(brief['targets'], 'targets')
    if any(t not in TARGET_SPECS or not t.startswith(('iphone_', 'ipad_')) for t in targets):
        raise ValueError('Unsupported CPP target')
    verified(root, brief['releaseEvidence'])
    if datetime.fromisoformat(required(stock, 'observedAt')).tzinfo is None:
        raise ValueError('Inventory needs an observation timezone')
    if not brief['appId'].isascii() or not brief['appId'].isdigit():
        raise ValueError('Expected numeric App Store app ID')
    pages = stock['pages']
    if not isinstance(pages, list):
        raise ValueError('Invalid page inventory')
    by_id = {required(p, 'pageId'): p for p in pages}
    if len(by_id) != len(pages):
        raise ValueError('Ambiguous page inventory')
    decision = draft['decision']
    if decision not in ('createPage', 'updatePage', 'reusePage', 'reuseDefault', 'needsEvidence'):
        raise ValueError('Unknown CPP decision')
    selected = by_id.get(draft.get('pageId'))
    if decision in ('updatePage', 'reusePage') and selected is None:
        raise ValueError('Select a page from the inventory')
    if decision in ('createPage', 'reuseDefault') and draft.get('pageId') is not None:
        raise ValueError('Unexpected existing page ID')
    gaps = list(strings(draft.get('gaps', []), 'gaps', empty=True))
    if stock.get('complete') is not True:
        gaps.append('Refresh the complete page inventory')
    if decision == 'createPage' and len(pages) >= 70:
        gaps.append('CPP page quota reached')
    if decision == 'createPage' and any(p.get('name') == draft.get('name') for p in pages):
        gaps.append('Resolve the existing same-name page before creating')
    link = 'https://apps.apple.com/app/id' + brief['appId'] if decision == 'reuseDefault' else None
    if decision == 'reusePage':
        link = checked_url(selected, brief['appId'])
        if not link or selected.get('approved') is not True or selected.get('visible') is not True:
            gaps.append('Verify approved visible page and its URL')
    assets = stock['assets']
    baseline = stock['defaultPage']
    editable = decision in ('createPage', 'updatePage')
    if editable:
        required(draft, 'name')
        if not draft.get('claims'):
            gaps.append('Provide released feature evidence for the proposed copy')
        for claim in draft.get('claims', []):
            required(claim, 'text')
            for ref in strings(claim['evidenceRefs'], 'claim evidence'):
                evidence = stock['evidence'].get(ref)
                if not evidence or evidence.get('releaseSha256') != brief['releaseEvidence']['sha256']:
                    gaps.append(f'Verify release evidence {ref}')
                else:
                    verified(root, evidence)
                    if claim['text'] not in evidence.get('supports', []):
                        gaps.append(f'Confirm that {ref} supports the claim: {claim["text"]}')
        if draft.get('deepLink'):
            ref = stock.get('routes', {}).get(draft['deepLink'])
            if not ref or ref.get('releaseSha256') != brief['releaseEvidence']['sha256']:
                gaps.append('Verify the deep link on the release build')
            else:
                verified(root, ref)
    desired = draft.get('localizations', {}) if editable else (selected or baseline).get('localizations', {})
    if editable and set(desired) != set(locales):
        gaps.append('Provide each requested localization')
    rows = []
    for locale in locales:
        default = baseline.get('localizations', {}).get(locale, {})
        before = (selected or baseline).get('localizations', {}).get(locale, {})
        after = desired.get(locale, {})
        copy = after.get('promotionalText', before.get('promotionalText', ''))
        if not isinstance(copy, str) or len(copy) > 170:
            raise ValueError('Invalid promotional text')
        keywords = strings(after.get('keywords', before.get('keywords', [])), 'keywords', empty=True)
        if editable and set(keywords) - set(stock.get('approvedKeywords', {}).get(locale, [])):
            gaps.append(f'Unapproved keyword in {locale}')
        if editable and keywords and any(
            p is not selected and set(p.get('localizations', {}).get(locale, {}).get('keywords', [])) == set(keywords)
            for p in pages
        ):
            gaps.append(f'Keyword combination already assigned in {locale}')
        for target in targets:
            original = before.get('media', {}).get(target, [])
            groups = [strings(ids, 'media', empty=True) for ids in (
                default.get('media', {}).get(target, []), original, after.get('media', {}).get(target, original))]
            roles = [assets.get(aid, {}).get('role') for aid in groups[-1]]
            if roles.count('screenshot') > 10 or roles.count('preview') > 3:
                gaps.append(f'Media limit exceeded for {locale}/{target}: at most 10 screenshots and 3 previews')
            if not groups[-1]:
                gaps.append(f'Provide media for {locale}/{target}')
            for aid in dict.fromkeys(a for group in groups for a in group):
                if aid not in assets:
                    gaps.append(f'Capture or identify {aid} for {locale}/{target}')
                    continue
                asset = assets[aid]
                if asset['locale'] != locale or asset['target'] != target:
                    raise ValueError('Media locale or target mismatch')
                required(asset, 'artifactId')
                path = verified(root, asset)
                if asset['role'] == 'screenshot':
                    w, h, alpha = inspect_png(path.read_bytes())
                    if alpha:
                        raise ValueError('CPP screenshots must be opaque')
                    spec = TARGET_SPECS[target]
                    if sorted((w, h)) != sorted((spec['width'], spec['height'])):
                        raise ValueError('Screenshot dimensions do not match target')
                elif asset['role'] == 'preview' and path.suffix.lower() in ('.mov', '.mp4', '.m4v'):
                    poster = asset.get('poster')
                    if poster is not None:
                        if poster.get('previewSha256') != asset['sha256']:
                            raise ValueError('CPP poster belongs to a different preview')
                        inspect_png(verified(root, poster).read_bytes())
                    receipt = asset.get('validation')
                    if not receipt:
                        gaps.append(f'Provide managed preview validation for {aid}')
                    else:
                        validation = read(verified(root, receipt))
                        verified_video = any(row.get('sha256') == asset['sha256'] and row.get('type') == 'video'
                                             for row in validation.get('assets', {}).values())
                        if validation.get('status') != 'PASS' or not verified_video:
                            gaps.append(f'Validate the selected preview {aid}')
                else:
                    raise ValueError('Unsupported media')
            rows.append(dict(locale=locale, target=target, defaultMedia=groups[0], before=groups[1],
                             after=groups[2], beforeText=before.get('promotionalText', ''),
                             afterText=copy, beforeKeywords=before.get('keywords', []), keywords=keywords))
    if decision == 'needsEvidence' and not gaps:
        gaps.append('Supply missing campaign evidence')
    result = dict(schemaVersion=1, campaignKey=key, appId=brief['appId'], bundleId=brief['bundleId'],
                  decision=decision, rationale=required(draft, 'rationale'), pageId=draft.get('pageId'),
                  name=draft.get('name'), deepLink=draft.get('deepLink'), editDeepLink='deepLink' in draft, url=link,
                  rows=rows, sources=sources, inputDigests=list(map(digest, (brief, draft, stock))),
                  blockers=gaps, status='blocked' if gaps else 'ready')
    return {**result, 'planDigest': digest(result)}


def replay(root, key, path):
    supplied = read(inside(root, path))
    sources = supplied['sources']
    if not isinstance(sources, list) or len(sources) != 3:
        raise ValueError('Invalid CPP plan sources')
    current = compile_plan(root, key, sources[1], sources[2])
    if current != supplied:
        raise ValueError('Stale or modified CPP plan; run cpp plan again')
    return current


def add_commands(parent):
    group = parent.add_subparsers(dest='cpp_action', required=True)
    discover = group.add_parser('discover', help='Read the complete CPP page, version and localization inventory from ASC')
    discover.add_argument('--app', required=True)
    discover.add_argument('--repo', type=Path, default=argparse.SUPPRESS)
    discover.add_argument('--json', action='store_true')
    actions = {
        'plan': 'Check the campaign proposal and compare existing pages',
        'preview': 'Export the reviewed media and side-by-side comparison',
        'handoff': 'Reconcile a reviewed plan with observed CPP resources',
        'claim': 'Reserve one external operation in the campaign ledger',
        'reconcile': 'Verify an outstanding claim against observed state',
        'status': 'Read the latest observed page, version and URL',
        'report': 'Import daily detailed Apple acquisition report segments',
    }
    for name, help_text in actions.items():
        cmd = group.add_parser(name, help=help_text)
        cmd.add_argument('--repo', type=Path, default=argparse.SUPPRESS)
        cmd.add_argument('--json', action='store_true')
        cmd.add_argument('--campaign', required=True)
        if name == 'plan':
            cmd.add_argument('--proposal', type=Path)
            cmd.add_argument('--inventory', type=Path)
        if name in ('preview', 'handoff', 'claim', 'reconcile'):
            cmd.add_argument('--plan', type=Path, required=True)
        if name in ('claim', 'reconcile'):
            cmd.add_argument('--operation', required=True)
        if name in ('preview', 'handoff'):
            cmd.add_argument('--out', type=Path, required=True)
        if name in ('handoff', 'status', 'report', 'claim', 'reconcile'):
            cmd.add_argument('--observation', type=Path)
        if name == 'reconcile':
            cmd.add_argument('--rejection', type=Path, help='Receipt for a confirmed permanent ASC rejection')
        if name == 'report':
            cmd.add_argument('--input', type=Path, required=True)
            cmd.add_argument('--from', dest='start', required=True)
            cmd.add_argument('--to', dest='end', required=True)


def execute(root, args):
    from cpp_delivery import handoff, preview, status, write_output
    from cpp_report import report
    if args.cpp_action == 'discover':
        from cpp_discovery import discover
        return discover(args.app)
    key = args.campaign
    base = campaign_dir(root, key)
    action = args.cpp_action
    if action == 'plan':
        return compile_plan(root, key, args.proposal, args.inventory)
    if action in ('claim', 'reconcile'):
        from cpp_operations import transition
        if action == 'reconcile':
            plan = read(inside(root, args.plan))
            body = {k: v for k, v in plan.items() if k != 'planDigest'}
            if plan.get('campaignKey') != key or digest(body) != plan.get('planDigest'):
                raise ValueError('Invalid original claim plan')
        else:
            plan = replay(root, key, args.plan)
            if plan['blockers']:
                return plan
        return transition(root, plan, args.observation, args.operation, action, getattr(args, 'rejection', None))
    if action in ('handoff', 'preview'):
        plan = replay(root, key, args.plan)
        if action == 'preview':
            return preview(root, plan, inside(root, args.out))
        if plan['blockers']:
            return plan
        result = handoff(root, plan, args.observation)
        write_output(inside(root, args.out), result)
        return result
    brief = read(inside(root, base / 'brief.json'))
    observed = status(root, key, brief, args.observation)
    if action == 'status':
        return observed
    return report(root, observed, inside(root, args.input), args.start, args.end)
