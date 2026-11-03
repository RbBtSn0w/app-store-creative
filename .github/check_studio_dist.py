#!/usr/bin/env python3
"""Fail if Studio's built runtime assets differ from committed Git content."""
import argparse
from pathlib import Path
import subprocess
import sys

DIST = 'plugins/app-store-creative/skills/app-store-creative/runtime/studio/dist'


def check(repo: Path, dist: str) -> list[str]:
    repo = repo.resolve()
    target = (repo / dist).absolute()
    target.relative_to(repo)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    changed = git('diff', '--name-only', '-z', 'HEAD', '--', dist)
    # Deliberately omit --exclude-standard: ignored build debris is stale too.
    extras = git('ls-files', '--others', '-z', '--', dist)
    return sorted(set(part.decode('utf-8', 'surrogateescape')
                      for part in (changed + extras).split(b'\0') if part))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dist', default=DIST)
    args = parser.parse_args()
    paths = check(args.repo, args.dist)
    if paths:
        print('Studio runtime dist differs from Git HEAD:', file=sys.stderr)
        for path in paths:
            print(f'  {path}', file=sys.stderr)
        return 1
    print('Studio runtime dist matches Git HEAD.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
