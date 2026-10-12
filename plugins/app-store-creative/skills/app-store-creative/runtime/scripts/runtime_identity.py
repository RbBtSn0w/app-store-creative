"""Portable fingerprint of the producer source payload observed at initialization."""
import hashlib
import json
from pathlib import Path
import re


def validate(value):
    if (not isinstance(value, dict) or set(value) != {'scheme', 'sha256', 'file_count'}
            or value['scheme'] != 'source-payload-sha256-v1'
            or not isinstance(value['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['sha256'])
            or type(value['file_count']) is not int or value['file_count'] < 1):
        raise ValueError('Invalid producer implementation identity')
    return value


def snapshot(directory=None):
    root = Path(directory) if directory is not None else Path(__file__).resolve().parent
    entries = []
    for path in sorted(root.iterdir()):
        if path.suffix not in ('.py', '.swift'):
            continue
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ValueError('Producer payload identity requires regular source files')
        entries.append([path.name, hashlib.sha256(path.read_bytes()).hexdigest()])
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return validate({'scheme': 'source-payload-sha256-v1',
                     'sha256': hashlib.sha256(payload).hexdigest(), 'file_count': len(entries)})
