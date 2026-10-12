"""Local ASC handoffs bound to immutable archives and actual Git commits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


def committed_archive(root, package, commit, manifest, archive_path=None):
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ValueError('Archive commit must be a full hexadecimal commit identity')
    root = Path(root).resolve(); package = Path(package).resolve()
    from delivery_lifecycle import relative_name
    if archive_path is None:
        if not package.is_relative_to(root):
            raise ValueError('Git archive must be inside the repository')
        relative = package.relative_to(root).as_posix()
    else:
        relative = relative_name(archive_path)
    def blob(name):
        result = subprocess.run(['git', '-C', str(root), 'show', f'{commit}:{name}'], capture_output=True)
        if result.returncode:
            raise ValueError('Archive is not persisted at the specified Git commit')
        return result.stdout
    from artifact_lifecycle import digest
    manifest_bytes = blob(relative + '/manifest.json')
    if hashlib.sha256(manifest_bytes).hexdigest() != digest(package / 'manifest.json'):
        raise ValueError('Git archive manifest differs from sealed delivery')
    for record in manifest['files']:
        data = blob(relative + '/' + record['path'])
        if data.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
            raise ValueError('LFS archive needs remote retrieval verification before publication')
        if len(data) != record['size_bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Git archive media or recipe integrity failure')
    return relative


class PublicationOperations:
    def plan_publication(self, delivery_id, archive_commit, remote_target):
        from artifact_lifecycle import canonical, identifier
        from delivery_lifecycle import verify_archive
        with self.transaction():
            delivery = self._read('deliveries', delivery_id)
            if not isinstance(remote_target, dict) or not all(remote_target.get(k) for k in ('app_id', 'version_id', 'platform')):
                raise ValueError('Explicit ASC app, version resource and platform are required')
            if remote_target['platform'] != delivery['target']['platform']:
                raise ValueError('Remote platform does not match the approved delivery')
            package = self.delivery_path(delivery)
            verify_archive(package, delivery['manifest_sha256'])
            manifest = json.loads((package / 'manifest.json').read_text())
            original = Path(delivery['local_path'])
            if not original.is_relative_to(self.paths.project):
                raise ValueError('Original Git archive location must be inside the repository')
            relative = committed_archive(self.paths.project, package, archive_commit, manifest,
                                         original.relative_to(self.paths.project).as_posix())
            config = json.loads((package / 'recipe/config.json').read_text())
            assets = []
            for asset in manifest['assets']:
                data = (package / asset['path']).read_bytes()
                metadata = {'path': relative + '/' + asset['path'], 'artifact_id': asset['artifact_id'],
                            'role': asset['role'], 'sha256': asset['sha256'], 'source_checksum': hashlib.md5(data).hexdigest()}
                if asset['role'] == 'preview':
                    metadata['poster_frame_time_code'] = config.get('previewVideo', {}).get('posterFrameTimeCode')
                assets.append(metadata)
            identity = identifier()
            body = {'id': identity, 'delivery_id': delivery_id, 'target': remote_target,
                    'archive_commit': archive_commit, 'manifest_sha256': delivery['manifest_sha256'],
                    'archive_path': relative, 'assets': assets, 'executor': 'official-asc-plugin',
                    'remote_write': False, 'required_actions': ['Resolve and confirm version localization resources',
                        'Obtain explicit upload approval for this plan hash', 'Execute through the official ASC plugin',
                        'Record processing, media and poster observations separately'],
                    'idempotency_key': hashlib.sha256(canonical({'delivery': delivery['manifest_sha256'], 'target': remote_target})).hexdigest()}
            return self._record('publications', body, 'plan')

    def approve_upload(self, publication_id, actor, authorization_reference):
        from artifact_lifecycle import canonical, identifier
        if not actor or not authorization_reference:
            raise ValueError('Explicit human actor and authorization reference are required')
        with self.transaction():
            plan = self._read('publications', publication_id, 'plan')
            delivery = self._read('deliveries', plan['delivery_id'])
            from delivery_lifecycle import verify_archive
            package = self.delivery_path(delivery); verify_archive(package, delivery['manifest_sha256'])
            committed_archive(self.paths.project, package, plan['archive_commit'],
                              json.loads((package / 'manifest.json').read_text()), plan['archive_path'])
            return self._record('approvals', {'id': identifier(), 'stage': 'upload', 'actor': actor,
                'authorization_reference': authorization_reference, 'publication_id': publication_id,
                'plan_sha256': hashlib.sha256(canonical(plan)).hexdigest(), 'target': plan['target']})

    def publication_status(self, publication_id, max_age_seconds=86400):
        return self._publication_state(publication_id, max_age_seconds)

    def export_publication(self, publication_id, write=False):
        from artifact_lifecycle import canonical
        from delivery_lifecycle import verify_archive
        with self.transaction():
            plan = self._read('publications', publication_id, 'plan')
            delivery = self._read('deliveries', plan['delivery_id'])
            package = self.delivery_path(delivery); verify_archive(package, delivery['manifest_sha256'])
            committed_archive(self.paths.project, package, plan['archive_commit'],
                              json.loads((package / 'manifest.json').read_text()), plan['archive_path'])
            plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
            approvals = [self._read('approvals', path.stem)
                         for path in (self.paths.workspace / 'records/approvals').glob('*.json')]
            approved = any(item.get('stage') == 'upload' and item.get('publication_id') == publication_id
                           and item.get('plan_sha256') == plan_hash for item in approvals)
            result = {'publication_id': publication_id, 'uploaded': False, 'remote_write': False,
                      'executor': 'official-asc-plugin', 'plan_sha256': plan_hash,
                      'upload_approval': 'approved' if approved else 'pending', 'handoff': plan}
            if write:
                target = self.paths.publications / publication_id / 'plan.json'
                if target.resolve() != target:
                    raise ValueError('Publication path is symlinked')
                if target.exists():
                    if target.read_bytes() != canonical(plan):
                        raise ValueError('Existing immutable handoff differs from publication plan')
                else:
                    self._write_path(target, plan)
                result['handoff_path'] = str(target)
                result['observations_exported'] = self._export_observation_records(publication_id, plan_hash)
            return result
