"""Stable project identity shared by configuration and execution boundaries."""


def require_project_identity(config):
    project = config.get('project') if isinstance(config, dict) else None
    identity = project.get('id') if isinstance(project, dict) else None
    if (not isinstance(identity, str) or not identity.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in identity)):
        raise ValueError('Project identity must be a nonempty string without control characters')
    return identity
