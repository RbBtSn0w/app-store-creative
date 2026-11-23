"""Read scoped CPP resources through the installed ASC CLI."""
import json
import subprocess
from datetime import datetime, timezone

from cpp_campaign import required


class AscReadError(RuntimeError):
    """ASC could not complete a read-only request."""


def discover(app_id):
    if not app_id.isascii() or not app_id.isdigit():
        raise ValueError('Expected numeric app ID')
    def listing(args, kind):
        command = ['asc', 'product-pages', 'custom-pages', *args, '--paginate', '--output', 'json']
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AscReadError(f'ASC {kind} listing unavailable: {error}') from error
        if result.returncode:
            raise AscReadError(f'ASC {kind} listing failed ({result.returncode}): {result.stderr.strip()[:500]}')
        payload = json.loads(result.stdout)
        rows = payload.get('data')
        if not isinstance(rows, list) or payload.get('links', {}).get('next'):
            raise ValueError(f'Incomplete ASC {kind} listing')
        ids = set()
        for row in rows:
            if row.get('type') != kind or required(row, 'id') in ids:
                raise ValueError(f'Unexpected or duplicate {kind} resource')
            ids.add(row['id'])
        return rows
    def parent(row, name, expected):
        relationship = row.get('relationships', {}).get(name, {})
        if 'data' in relationship and relationship['data'].get('id') != expected:
            raise ValueError(f'ASC {name} relationship mismatch')
    pages = listing(['list', '--app', app_id, '--include', 'app'], 'appCustomProductPages')
    records = []
    for page in pages:
        parent(page, 'app', app_id)
        versions = listing(['versions', 'list', '--custom-page-id', page['id']], 'appCustomProductPageVersions')
        members = []
        for version in versions:
            parent(version, 'appCustomProductPage', page['id'])
            localizations = listing(['localizations', 'list', '--custom-page-version-id', version['id']],
                                    'appCustomProductPageLocalizations')
            for loc in localizations:
                parent(loc, 'appCustomProductPageVersion', version['id'])
            members.append(dict(version=version, localizations=localizations))
        records.append(dict(page=page, versions=members))
    return dict(schemaVersion=1, appId=app_id, observedAt=datetime.now(timezone.utc).isoformat(),
                source='asc', pages=records, remoteWrite=False)
