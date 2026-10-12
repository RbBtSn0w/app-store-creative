"""Read-only local object inventory and explicitly scoped capacity estimates."""
import os
from pathlib import Path
import re


def files_without_links(root):
    files, links = [], []
    if root.is_symlink():
        return [], [root]
    if not root.exists():
        return files, links
    for directory, children, names in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in list(children):
            path = base / name
            if path.is_symlink():
                links.append(path); children.remove(name)
        for name in names:
            path = base / name
            if path.is_symlink():
                links.append(path)
            elif path.is_file():
                files.append(path)
    return files, links


class InventoryOperations:
    def _object_inventory(self):
        from artifact_lifecycle import digest
        self._assert_paths()
        records = self.paths.workspace / 'records'
        artifacts = [self._read('artifacts', p.stem) for p in (records / 'artifacts').glob('*.json')]
        registered = {}
        for artifact in artifacts:
            registered.setdefault(artifact['sha256'], []).append(artifact)
        active, quarantine, unknown = {}, [], []
        object_files, links = files_without_links(self.paths.objects)
        for path in object_files:
            relative = path.relative_to(self.paths.objects)
            if len(relative.parts) == 2 and re.fullmatch('[0-9a-f]{64}', path.name) and relative.parts[0] == path.name[:2]:
                active[path.name] = path
            elif relative.parts[0] == '.quarantine':
                quarantine.append(path)
            elif relative.as_posix() != '_owner.json':
                unknown.append(path)
        valid_quarantine, corrupt_quarantine, known_quarantine, purged = set(), [], set(), set()
        for path in (records / 'maintenance').glob('*.json'):
            operation = self._read('maintenance', path.stem)
            if operation.get('operation') != 'quarantine':
                continue
            purged_path = self._path('maintenance', operation['id'], 'purged')
            if purged_path.exists():
                result = self._read('maintenance', operation['id'], 'purged')
                if result['status'] == 'purged':
                    purged.update(item['sha256'] for item in operation['objects'])
            for item in operation['objects']:
                try:
                    stored = self._quarantine_path(operation['id'], item['sha256'])
                except ValueError:
                    corrupt_quarantine.append(str(self.paths.objects / '.quarantine' / operation['id'] / item['sha256']))
                    continue
                known_quarantine.add(stored)
                if stored in quarantine:
                    if stored.stat().st_size == item['size_bytes'] and digest(stored) == item['sha256']:
                        valid_quarantine.add(item['sha256'])
                    else:
                        corrupt_quarantine.append(str(stored))
        corrupt = []
        for sha, path in active.items():
            if sha in registered:
                sizes = {a['size_bytes'] for a in registered[sha]}
                if sizes != {path.stat().st_size} or digest(path) != sha:
                    corrupt.append(sha)
        missing = sorted(set(registered) - set(active) - valid_quarantine - purged)
        payloads = list(active.values()) + quarantine
        inode_blocks = {}
        for path in payloads:
            stat = path.stat()
            inode_blocks[(stat.st_dev, stat.st_ino)] = getattr(stat, 'st_blocks', 0) * 512
        def size(paths):
            return sum(path.stat().st_size for path in paths)
        work, work_links = files_without_links(self.paths.workspace / 'work')
        releases, release_links = files_without_links(self.paths.releases)
        publications, publication_links = files_without_links(self.paths.publications)
        return {'objects': {
                    'reference_count': len(artifacts), 'registered_identities': len(registered),
                    'active_count': len(active), 'corrupt': sorted(corrupt), 'missing': missing,
                    'quarantined': sorted(valid_quarantine - set(active)),
                    'purged': sorted(purged - set(active) - valid_quarantine),
                    'orphan_files': sorted(str(path) for sha, path in active.items() if sha not in registered),
                    'unknown_files': sorted(str(path) for path in unknown),
                    'unknown_quarantine_files': sorted(str(path) for path in quarantine if path not in known_quarantine),
                    'corrupt_quarantine_files': sorted(corrupt_quarantine),
                    'unsafe_links': sorted(str(path) for path in links)},
                'capacity': {'active_object_bytes': size(active.values()), 'quarantine_file_bytes': size(quarantine),
                    'other_object_file_bytes': size(unknown), 'work_file_bytes': size(work),
                    'release_directory_bytes': size(releases), 'publication_directory_bytes': size(publications),
                    'payload_logical_bytes': size(payloads), 'payload_unique_inodes': len(inode_blocks),
                    'payload_allocated_bytes_estimate': sum(inode_blocks.values()),
                    'estimate_caveat': 'Local stat blocks; shared filesystem extents and compression are not resolved',
                    'git_history_bytes': None, 'lfs_remote_bytes': None, 'external_backend_bytes': None},
                'other_unsafe_links': sorted(str(path) for path in work_links + release_links + publication_links),
                'scope': 'Observed local files; not a cleanup plan or remote storage verification'}
