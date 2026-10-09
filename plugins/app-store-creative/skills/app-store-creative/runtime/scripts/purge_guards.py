"""Exact reference and filesystem guards retained across interrupted purge."""
import hashlib
from pathlib import Path

from artifact_lifecycle import canonical, digest
from inventory_lifecycle import files_without_links
from relocation_quarantine import _identity


def references(core):
    records = core.paths.workspace / 'records'; items = []
    for path in sorted(records.rglob('*.json')):
        if 'maintenance' in path.relative_to(records).parts:
            continue
        if path.resolve() != path:
            raise ValueError('Purge reference contains aliases')
        items.append([path.relative_to(records).as_posix(), digest(path)])
    return hashlib.sha256(canonical({'config': core._live_configuration(), 'records': items})).hexdigest()


def scan(roots):
    result = []
    for root, expected in sorted(roots.items()):
        path = Path(root)
        if path.resolve() != path or not path.is_dir() or _identity(path) != expected:
            raise ValueError('Purge guard root identity changed')
        files, links = files_without_links(path, strict=True)
        if links:
            raise ValueError('Purge guard contains unsafe links')
        for file in files:
            result.append({'path': str(file), 'sha256': digest(file), 'size_bytes': file.stat().st_size,
                           'file_identity': _identity(file)})
    return sorted(result, key=lambda item: item['path'])
