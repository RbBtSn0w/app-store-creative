"""Canonical record bytes, identities and traversal without business dependencies."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return uuid.uuid4().hex


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', value):
        raise ValueError('Invalid record identity')
    return value


def dependency_closure(identities, load):
    """Traverse dependencies without consuming the interpreter call stack."""
    results = {}; pending = {}; active = set()
    stack = [(identity, False) for identity in reversed(list(identities))]
    while stack:
        identity, exiting = stack.pop()
        if exiting:
            active.remove(identity)
            results[identity] = pending.pop(identity)
            continue
        if identity in results:
            continue
        if identity in active:
            raise ValueError('Artifact dependency cycle')
        record = load(identity)
        active.add(identity); pending[identity] = record
        stack.append((identity, True))
        stack.extend((parent, False) for parent in reversed(record['inputs']))
    return results
