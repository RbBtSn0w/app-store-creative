"""Review and reconciled handoff for a CPP. All remote mutations belong to the ASC executor."""
import hashlib
import json
import os
import tempfile
from datetime import datetime
from html import escape
from pathlib import Path

from cpp_campaign import campaign_dir, checked_url, digest, inside, read, required, verified


def put(path, content):
    """Publish immutable output atomically, allowing identical retries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        name = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush()
            try:
                os.link(name, path)
            except FileExistsError:
                if path.is_symlink() or path.read_bytes() != content:
                    raise ValueError(f'Choose a new output path: {path}')
        finally:
            name.unlink(missing_ok=True)


def write_output(path, obj):
    put(path, (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode())


def review_html(plan, media):
    parts = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             '<title>Custom product page review</title><style>body{font:16px system-ui;max-width:90rem;margin:auto;padding:1rem}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,20rem),1fr));gap:1rem}img,video{max-width:100%;max-height:22rem}figure{display:inline-block;margin:.4rem}figcaption{overflow-wrap:anywhere}</style>',
             f'<h1>{escape(plan["campaignKey"])}</h1><p>{escape(plan["decision"])} · {escape(plan["rationale"])}</p>']
    for gap in plan['blockers']:
        parts.append(f'<p role="alert">{escape(gap)}</p>')
    for row in plan['rows']:
        parts.append(f'<h2>{escape(row["locale"])} · {escape(row["target"])}</h2><section>')
        columns = [('Default page', 'defaultMedia'), ('Proposed page', 'after')]
        if row['before'] != row['defaultMedia']:
            columns.insert(1, ('Current custom page', 'before'))
        for title, key in columns:
            parts.append(f'<article><h3>{title}</h3>')
            for aid in row[key]:
                if aid not in media:
                    parts.append(f'<p>Missing media: {escape(aid)}</p>')
                    continue
                role, src = media[aid]
                poster = media.get((aid, 'poster'))
                poster_attr = f' poster="{escape(poster[1])}"' if poster else ''
                tag = (f'<img alt="{escape(aid)}" src="{escape(src)}">' if role == 'screenshot'
                       else f'<video controls preload="metadata"{poster_attr} src="{escape(src)}"></video>')
                parts.append(f'<figure>{tag}<figcaption>{escape(aid)}</figcaption></figure>')
            parts.append('</article>')
        parts.append('</section>')
        for label, value in [('Current text', row['beforeText']), ('Proposed text', row['afterText']),
                             ('Keywords', ', '.join(row['keywords']))]:
            parts.append(f'<p><strong>{label}</strong> {escape(value)}</p>')
    return ''.join(parts).encode()


def review_assets(root, plan):
    catalog = read(inside(root, plan['sources'][2]))['assets']
    for aid in dict.fromkeys(a for row in plan['rows'] for k in ('defaultMedia', 'before', 'after') for a in row[k]):
        if aid not in catalog:
            continue
        ref = catalog[aid]
        path = verified(root, ref)
        suffix = '.png' if ref['role'] == 'screenshot' else path.suffix.lower()
        yield aid, ref['role'], ref['sha256'] + suffix, path
        if ref['role'] == 'preview' and ref.get('poster'):
            poster = ref['poster']
            yield (aid, 'poster'), 'poster', poster['sha256'] + '.png', verified(root, poster)


def preview(root, plan, output):
    media = {}
    for aid, role, filename, path in review_assets(root, plan):
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != filename.split('.')[0]:
            raise ValueError('Media changed during review export')
        put(inside(root, output / 'media' / filename), data)
        media[aid] = role, 'media/' + filename
    path = inside(root, output / 'index.html')
    put(path, review_html(plan, media))
    return dict(status=plan['status'], planDigest=plan['planDigest'], path=str(path), blockers=plan['blockers'])


def status(root, key, brief, path):
    explicit = path is not None
    path = inside(root, path or campaign_dir(root, key) / 'observation.json')
    if brief.get('campaignKey') != key:
        raise ValueError('Campaign identity mismatch')
    if not path.exists():
        if explicit:
            raise ValueError('Specified observation is missing')
        return dict(status='unobserved', campaignKey=key)
    obs = read(path)
    for field in ('appId', 'bundleId', 'campaignKey'):
        if required(obs, field) != required(brief, field):
            raise ValueError('Observation belongs to another campaign or app')
    if datetime.fromisoformat(required(obs, 'observedAt')).tzinfo is None:
        raise ValueError('Observation needs a timezone')
    # The executor retains the original normalized snapshot as an immutable input.
    snap = read(verified(root, obs['evidence']))
    if required(snap, 'appId') != obs['appId'] or required(snap, 'bundleId') != obs['bundleId']:
        raise ValueError('Cross-app page observation')
    page = snap['page']
    if required(page, 'pageId') != required(obs, 'pageId'):
        raise ValueError('Page ID mismatch')
    version = snap['version']
    if required(version, 'pageId') != page['pageId'] or required(version, 'pageVersionId') != required(obs, 'pageVersionId'):
        raise ValueError('Page version relationship mismatch')
    locales = version['localizations']
    ids = set()
    for loc in locales.values():
        loc_id = required(loc, 'localizationId')
        if required(loc, 'pageVersionId') != version['pageVersionId'] or loc_id in ids:
            raise ValueError('Localization relationship mismatch')
        ids.add(loc_id)
    url = checked_url(page, obs['appId']) if page.get('visible') is True and page.get('approved') is True else None
    return dict(status='observed', campaignKey=key, appId=obs['appId'], bundleId=obs['bundleId'],
                pageId=page['pageId'], pageVersionId=version['pageVersionId'], name=required(page, 'name'),
                observedAt=obs['observedAt'], evidenceSha256=obs['evidence']['sha256'],
                reviewState=required(version, 'state'), url=url, localizations=locales,
                deepLink=version.get('deepLink'), planDigest=obs.get('planDigest'),
                versionInventory=snap.get('versionInventory'))


def handoff(root, plan, observation):
    result = dict(schemaVersion=1, status='ready', campaignKey=plan['campaignKey'],
                  planDigest=plan['planDigest'], executor='official-asc-plugin', remoteWrite=False,
                  decision=plan['decision'], operations=[])
    if plan['decision'] in ('reusePage', 'reuseDefault'):
        return {**result, 'phase': 'reuse', 'url': plan['url']}
    from asc_display_types import IOS_SCREENSHOT_TYPES
    brief, _, stock = [read(inside(root, p)) for p in plan['sources']]
    obs = status(root, plan['campaignKey'], brief, observation)
    ops = result['operations']

    def add(kind, scope, desired):
        body = dict(kind=kind, scope=scope, desired=desired)
        ops.append({**body, 'operationId': digest([plan['appId'], plan['campaignKey'], body])})

    if obs['status'] == 'unobserved':
        if plan['decision'] == 'createPage':
            add('preparePage', {'appId': plan['appId']}, {'name': plan['name']})
        return {**result, 'phase': 'resolveDraft', 'pageId': plan['pageId']}
    if plan['decision'] == 'createPage' and obs['name'] != plan['name']:
        raise ValueError('Prepared page name differs from plan')
    if obs['planDigest'] != plan['planDigest'] or (plan['pageId'] and obs['pageId'] != plan['pageId']):
        raise ValueError('Observation is not bound to this plan and page')
    target = dict(kind='customProductPageVersion', app_id=obs['appId'], bundle_id=obs['bundleId'],
                  page_id=obs['pageId'], page_version_id=obs['pageVersionId'], platform='IOS')
    result.update(target=target, observationSha256=obs['evidenceSha256'])
    if obs['reviewState'] not in ('PREPARE_FOR_SUBMISSION', 'REJECTED', 'APPROVED'):
        return {**result, 'phase': 'observe', 'reviewState': obs['reviewState'], 'url': obs['url']}
    if plan['editDeepLink'] and plan['deepLink'] != obs['deepLink']:
        add('updateDeepLink', target, plan['deepLink'])
    pending = []
    for locale in brief['locales']:
        loc = obs['localizations'].get(locale)
        if loc is None:
            add('prepareLocalization', target, locale)
            continue
        scope = {**target, 'locale': locale, 'cpp_localization_id': loc['localizationId']}
        rows = [row for row in plan['rows'] if row['locale'] == locale]
        text = rows[0]['afterText']
        keywords = rows[0]['keywords']
        if loc['promotionalText'] != text:
            add('updateText', scope, text)
        if sorted(loc['keywords']) != sorted(keywords):
            add('replaceKeywords', scope, keywords)
        for row in rows:
            assets = [{k: stock['assets'][a][k] for k in ('sha256', 'role', 'artifactId')}
                      for a in row['after']]
            existing = loc['media'].get(row['target'], [])
            if not isinstance(existing, list) or any(not isinstance(v, str) for v in existing):
                raise ValueError('Expected observed media digests in display order')
            if [a['sha256'] for a in assets] != existing:
                set_ids = loc.get('setIds', {}).get(row['target'], {})
                if existing and not set_ids and obs['reviewState'] != 'APPROVED':
                    raise ValueError('Resolve existing remote media set IDs before replacement')
                add('reconcileMedia', {**scope, 'target': row['target'], 'ordered_assets': assets,
                                       'display_type': IOS_SCREENSHOT_TYPES[row['target']], 'set_ids': set_ids,
                                       'plan_digest': plan['planDigest']},
                    {'before': existing, 'after': assets})
            else:
                for asset in assets:
                    gates = loc.get('readiness', {}).get(row['target'], {}).get(asset['sha256'], {})
                    expected = ['upload', 'processing', 'media']
                    if asset['role'] == 'preview':
                        expected.append('poster')
                    missing = [gate for gate in expected if gates.get(gate) is not True]
                    if missing:
                        pending.append(dict(locale=locale, target=row['target'], artifactId=asset['artifactId'],
                                            missing=missing))
    if obs['reviewState'] == 'APPROVED':
        if ops and plan['decision'] == 'updatePage':
            ops.clear()
            versions = obs['versionInventory']
            if not isinstance(versions, list) or not any(v.get('pageVersionId') == obs['pageVersionId']
                                                        and v.get('state') == 'APPROVED' for v in versions):
                return {**result, 'phase': 'resolveDraft', 'reasonCode': 'refreshAllVersions'}
            if any(v.get('state') not in ('APPROVED', 'REPLACED_WITH_NEW_VERSION') for v in versions):
                return {**result, 'phase': 'resolveDraft', 'reasonCode': 'resolveExistingVersion'}
            add('prepareVersion', target, {'previousVersionIds': sorted(required(v, 'pageVersionId') for v in versions)})
            return {**result, 'phase': 'resolveDraft'}
        return {**result, 'phase': 'observe', 'operations': [], 'reviewState': 'APPROVED', 'url': obs['url']}
    if ops:
        return {**result, 'phase': 'reconcile', 'pendingMedia': pending}
    if pending:
        return {**result, 'phase': 'verifyMedia', 'pendingMedia': pending}
    return {**result, 'phase': 'reviewHandoff',
            'reviewItem': {'type': 'appCustomProductPageVersions', 'id': obs['pageVersionId']}}
