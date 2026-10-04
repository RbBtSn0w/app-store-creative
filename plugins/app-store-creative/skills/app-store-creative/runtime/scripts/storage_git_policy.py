"""Inspect real Git state without editing user rules or the index."""
import os
from pathlib import Path
import subprocess


def git_environment():
    environment = dict(os.environ)
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
        environment.pop(key, None)
    environment['LC_ALL'] = 'C'
    return environment


def repository_for(path):
    directory = Path(path).parent
    while not directory.exists():
        if directory == directory.parent:
            return None
        directory = directory.parent
    try:
        result = subprocess.run(['git', '-C', str(directory), 'rev-parse', '--show-toplevel'],
            capture_output=True, env=git_environment())
    except OSError as error:
        raise ValueError('Git tooling unavailable for relocation safety verification') from error
    if result.returncode:
        if b'not a git repository' in result.stderr:
            return None
        raise ValueError('Git repository discovery could not be verified')
    return Path(os.fsdecode(result.stdout).rstrip('\n')).resolve()


def ignore_pattern(relative):
    return '/' + ''.join('\\' + char if char in '\\*?[]!#' else char for char in relative) + '/'


def staging_policy(staging):
    suggestions = {}
    for value in staging.values():
        path = Path(value)
        repository = repository_for(path)
        if repository is None:
            continue
        pattern = ignore_pattern(path.relative_to(repository).as_posix())
        suggestions.setdefault(str(repository), []).append(pattern)
    return {'staging': staging, 'gitignore': [pattern for patterns in suggestions.values() for pattern in patterns],
        'repositories': [{'root': root, 'gitignore_path': str(Path(root) / '.gitignore'), 'patterns': patterns}
                         for root, patterns in suggestions.items()], 'applied': False}


def verify_staging_ignored(staging):
    for value in staging.values():
        path = Path(value)
        repository = repository_for(path)
        if repository is None:
            continue
        relative = path.relative_to(repository).as_posix() + '/'
        tracked = subprocess.run(['git', '-C', str(repository), 'ls-files', '-z', '--', relative],
            capture_output=True, env=git_environment())
        if tracked.returncode:
            raise ValueError('Git index state could not be verified for relocation')
        if tracked.stdout:
            raise ValueError('Relocation staging has tracked Git entries')
        ignored = subprocess.run(['git', '-C', str(repository), 'check-ignore', '--quiet', '--no-index', '--', relative],
            capture_output=True, env=git_environment())
        if ignored.returncode == 1:
            raise ValueError('Relocation staging must be ignored by actual Git rules before copying')
        if ignored.returncode:
            raise ValueError('Git ignore state could not be verified for relocation')
