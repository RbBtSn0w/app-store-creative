"""Validate the shared archive declaration without inventing project choices."""
import re


def resolve(config, *, required=False):
    if 'archivePolicy' not in config:
        if required:
            raise ValueError('An explicit archive policy is required')
        return None
    raw = config['archivePolicy']
    if (not isinstance(raw, dict) or type(raw.get('schema_version')) is not int
            or raw['schema_version'] != 1
            or set(raw) - {'schema_version', 'mediaMode', 'backend'}):
        raise ValueError('Invalid archive policy schema or fields')
    mode = raw.get('mediaMode')
    if not isinstance(mode, str) or mode not in ('git', 'lfs', 'external'):
        raise ValueError('Invalid archive policy media mode')
    if mode == 'external':
        backend = raw.get('backend')
        if not isinstance(backend, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', backend):
            raise ValueError('External archive policy requires a named backend')
    elif 'backend' in raw:
        raise ValueError('Git and LFS archive policy cannot declare a backend')
    return dict(raw)


def require_retrieval(config, proof):
    policy = resolve(config, required=True)
    if not isinstance(proof, dict) or proof.get('media_mode') != policy['mediaMode']:
        raise ValueError('Retrieved media mode differs from archive policy')
    if policy['mediaMode'] == 'external' and proof.get('backend') != policy['backend']:
        raise ValueError('Retrieved backend differs from archive policy')
    return policy
