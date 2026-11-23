"""Read Apple detailed daily reports from an explicit set of versioned segments."""
import csv
import gzip
from datetime import date

from cpp_campaign import inside, read, required, verified


def report(root, observation, directory, start, end):
    start, end = date.fromisoformat(start), date.fromisoformat(end)
    if start > end or observation['status'] != 'observed':
        raise ValueError('Provide an ordered date range and a bound CPP observation')
    manifest = read(inside(root, directory / 'manifest.json'))
    if manifest.get('appId') != observation['appId'] or manifest.get('granularity') != 'daily':
        raise ValueError('Expected daily segments for this app')
    # Each revision describes a complete replacement, including all segments.
    revisions = {}
    for entry in manifest['instances']:
        key = (entry['type'], date.fromisoformat(entry['date']))
        if key[0] not in ('downloads', 'discovery') or type(entry['revision']) is not int or entry['revision'] < 0:
            raise ValueError('Invalid report instance')
        if not start <= key[1] <= end:
            continue
        revs = revisions.setdefault(key, {})
        if entry['revision'] in revs and revs[entry['revision']] != entry:
            raise ValueError('Conflicting report revisions')
        revs[entry['revision']] = entry
    totals, fingerprints = {}, []
    for (kind, day), revs in sorted(revisions.items()):
        mappings = [m for m in manifest['pageNames'] if date.fromisoformat(m['from']) <= day <= date.fromisoformat(m['to'])]
        titles = {required(m, 'title') for m in mappings if m['pageId'] == observation['pageId']}
        if len(titles) != 1 or any(m['title'] in titles and m['pageId'] != observation['pageId'] for m in mappings):
            raise ValueError(f'Missing or ambiguous page name mapping on {day}')
        entry = revs[max(revs)]
        seen = set()
        if not entry['segments']:
            raise ValueError('Missing report segments')
        for segment in entry['segments']:
            path = verified(directory, segment)
            if segment['sha256'] in seen:
                continue
            seen.add(segment['sha256'])
            fingerprints.append(segment['sha256'])
            opener = gzip.open if path.suffix == '.gz' else open
            with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream, delimiter='\t')
                field = 'Download Type' if kind == 'downloads' else 'Event'
                fields = {'Date', 'App Apple Identifier', 'Page Title', 'Page Type', 'Counts',
                          'Device', 'Territory', 'Source Type', field}
                if fields - set(reader.fieldnames or []):
                    raise ValueError('Unsupported detailed report headers')
                for row in reader:
                    if row['App Apple Identifier'] != observation['appId'] or row['Page Title'] not in titles:
                        continue
                    if row['Page Type'].lower() != 'product page':
                        continue
                    if date.fromisoformat(row['Date']) != day:
                        raise ValueError('Report rows span event dates; group the input by event date before import')
                    metric = {'Page view': 'pageViews', 'First-time Download': 'firstTimeDownloads',
                              'Redownload': 'redownloads'}.get(row[field])
                    if metric is None:
                        continue
                    count = int(row['Counts'])
                    if count < 0:
                        raise ValueError('Negative report count')
                    bucket = (day.isoformat(), row['Device'], row['Territory'], row['Source Type'], metric)
                    totals[bucket] = totals.get(bucket, 0) + count
    return dict(schemaVersion=1, status='reported', pageId=observation['pageId'],
                start=start.isoformat(), end=end.isoformat(), sourceDigests=fingerprints,
                coveredInstances=[{'report': kind, 'date': day.isoformat(), 'revision': max(revs)}
                                  for (kind, day), revs in sorted(revisions.items())],
                coverage='observedRows' if totals else 'noMatchingRows', conversionRate=None,
                conversionRateReason='No comparable deduplicated visitor denominator',
                rows=[dict(date=d, device=device, territory=t, source=s, metric=m, value=v)
                      for (d, device, t, s, m), v in sorted(totals.items())])
