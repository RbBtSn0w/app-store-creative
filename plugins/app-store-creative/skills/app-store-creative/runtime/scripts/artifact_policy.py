"""Strict operational project policy; missing declaration selects current defaults."""
DEFAULTS = {'schema_version': 1, 'trialRetentionDays': 30, 'diagnosticRetentionDays': 14,
            'quarantineDays': 7, 'mediaBudgetBytes': None}


def resolve(config):
    if 'artifactPolicy' not in config:
        return dict(DEFAULTS)
    raw = config['artifactPolicy']
    if (not isinstance(raw, dict) or type(raw.get('schema_version')) is not int
            or raw['schema_version'] != 1 or set(raw) - set(DEFAULTS)):
        raise ValueError('Unsupported artifact policy schema or fields')
    for key, value in raw.items():
        if key == 'schema_version':
            continue
        if type(value) is not int or value < 0:
            raise ValueError('Artifact policy values must be nonnegative integers')
    return {**DEFAULTS, **raw}


def inspect(core):
    import hashlib
    from artifact_lifecycle import canonical
    config = core._live_configuration()
    policy = resolve(config)
    return {'schema_version': 1, 'policy': policy,
            'policy_sha256': hashlib.sha256(canonical(policy)).hexdigest(),
            'source': 'project' if 'artifactPolicy' in config else 'defaults', 'writes_performed': False}


def require_media_budget(config):
    policy = resolve(config)
    declaration = config.get('artifactPolicy')
    if not isinstance(declaration, dict) or 'mediaBudgetBytes' not in declaration:
        raise ValueError('An explicit media budget is required for formal delivery')
    return policy['mediaBudgetBytes']
