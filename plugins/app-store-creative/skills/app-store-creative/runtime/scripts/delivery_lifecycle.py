"""Validated candidate approval and immutable, portable release packages."""
from __future__ import annotations

import contextlib
import ctypes
import errno
import os
import sys
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile


def relative_name(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('Artifact requires a portable relative path')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Artifact requires a safe relative path')
    return str(path)


def verify_archive(package, expected_sha256=None):
    from artifact_lifecycle import digest
    package = Path(package).resolve()
    manifest_path = package / 'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('Archive integrity: symlinked manifest')
    sha = digest(manifest_path)
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError('Archive manifest integrity failure')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema_version') != 1 or not manifest.get('files'):
        raise ValueError('Unsupported or incomplete archive manifest')
    names = set()
    for record in manifest['files']:
        name = relative_name(record['path'])
        if name in names or name == 'manifest.json':
            raise ValueError('Archive integrity: duplicate or self-referential file')
        names.add(name); path = package / name
        if (path.resolve() != path or not path.is_file()
                or path.stat().st_size != record['size_bytes'] or digest(path) != record['sha256']):
            raise ValueError(f'Archive integrity failure: {name}')
    actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != names | {'manifest.json'}:
        raise ValueError('Archive integrity: unexpected or missing files')
    for asset in manifest.get('assets', []):
        if asset['path'] not in names:
            raise ValueError('Archive media is not bound to file manifest')
    for source in manifest.get('recipe_inputs', []):
        if source['path'] not in names:
            raise ValueError('Archive recipe input is missing')
    if 'recipe/config.json' not in names or not manifest.get('assets'):
        raise ValueError('Archive recipe or media incomplete')
    import studio_contract
    recipe_config = json.loads((package / 'recipe/config.json').read_text())
    _, findings = studio_contract.input_hashes(package / 'recipe', recipe_config)
    preview = recipe_config.get('previewVideo', {})
    if preview.get('enabled'):
        source = relative_name(preview.get('source', ''))
        if 'recipe/' + source not in names:
            findings.append('Missing preview recipe source')
    if findings:
        raise ValueError('Archive recipe integrity: ' + '; '.join(findings))
    return {'package_verified': True, 'recipe_verified': True, 'manifest_sha256': sha,
            'assets_count': len(manifest['assets']), 'files_count': len(names)}


def commit_directory(staged, destination):
    """Publish a complete directory atomically without replacing an existing entry."""
    libc = ctypes.CDLL(None, use_errno=True)
    source, target = os.fsencode(staged), os.fsencode(destination)
    if sys.platform == 'darwin':
        call = libc.renamex_np
        call.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = call(source, target, 4)  # RENAME_EXCL, from the Darwin SDK.
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        call = libc.renameat2
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = call(-100, source, -100, target, 1)  # AT_FDCWD, RENAME_NOREPLACE.
    else:
        raise ValueError('Atomic directory publication is unavailable on this platform')
    if result:
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise ValueError('Destination already exists')
        raise OSError(code, os.strerror(code))


def restore_archive(package, destination, expected_sha256):
    package = Path(package).resolve(); destination = Path(destination)
    if destination.is_symlink() or destination.exists():
        raise ValueError('Restore destination already exists')
    destination = destination.resolve()
    if destination.is_relative_to(package) or package.is_relative_to(destination):
        raise ValueError('Restore destination overlaps source archive')
    verify_archive(package, expected_sha256)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.restoring-') as temporary:
        staged = Path(temporary) / 'package'
        shutil.copytree(package, staged, symlinks=True)
        result = verify_archive(staged, expected_sha256)
        if destination.exists() or destination.is_symlink():
            raise ValueError('Restore destination already exists')
        commit_directory(staged, destination)
    return {**result, 'restored_path': str(destination)}


class DeliveryOperations:
    def delivery_path(self, delivery):
        """Locate and verify an archive through its original immutable binding."""
        binding = delivery.get('storage')
        if not isinstance(binding, dict):
            raise ValueError('Delivery storage binding is missing')
        self.resolve_storage_binding(binding)
        original = Path(delivery['local_path'])
        root = Path(binding['releases'])
        if not original.is_absolute() or not original.is_relative_to(root):
            raise ValueError('Delivery location is outside its archive root')
        relative = original.relative_to(root)
        if not relative.parts or any(part in ('.', '..') for part in relative.parts):
            raise ValueError('Invalid delivery archive root location')
        package = self.paths.releases / relative
        if package.resolve() != package:
            raise ValueError('Delivery location contains a symlink')
        verify_archive(package, delivery['manifest_sha256'])
        return package

    def _candidate(self, candidate_id):
        from artifact_lifecycle import configuration_identity
        candidate = self._read('candidates', candidate_id)
        if self._path('candidate-dispositions', candidate_id).exists():
            raise ValueError('Candidate is discarded; select a new candidate')
        run = self._run(candidate['run_id'])
        if configuration_identity(self.config) != run['config_sha256']:
            raise ValueError('Candidate configuration changed; create a new run')
        from artifact_lifecycle import digest
        for name, expected in run.get('source_hashes', {}).items():
            import studio_contract
            source = studio_contract.local_asset(self.paths.project, name, run['config'])
            if not source.is_file() or digest(source) != expected:
                raise ValueError('Candidate source inputs changed; start a new run')
        for identity in candidate['artifacts']:
            self.verify_artifact(identity)
        return candidate, run

    def _closure(self, identities):
        results = {}; visiting = set()
        def visit(identity):
            if identity in visiting:
                raise ValueError('Artifact dependency cycle')
            if identity in results:
                return
            visiting.add(identity)
            record = self.verify_artifact(identity)
            for parent in record['inputs']:
                visit(parent)
            visiting.remove(identity); results[identity] = record
        for identity in identities:
            visit(identity)
        return results

    def _materialize(self, candidate, directory):
        media = directory / 'media'; recipe = directory / 'recipe'; media.mkdir(); recipe.mkdir()
        closure = self._closure(candidate['artifacts'])
        names = set()
        for identity, data in closure.items():
            name = relative_name(data.get('logical_path') or '')
            selected = identity in candidate['artifacts']
            target = (media if selected or data['role'] == 'render-evidence' else recipe) / name
            if target in names:
                if target.read_bytes() != self.object_path(data['sha256']).read_bytes():
                    raise ValueError('Conflicting logical artifact paths')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.object_path(data['sha256']), target)
            names.add(target)
        from input_lifecycle import write_snapshot_index
        write_snapshot_index(recipe, {data['logical_path']: data['sha256'] for data in closure.values()
            if data['role'] != 'render-evidence' and data['id'] not in candidate['artifacts']})
        return media, recipe, closure

    def validate_candidate(self, candidate_id):
        from artifact_lifecycle import canonical, identifier
        import hashlib
        import validator
        with self.transaction():
            candidate, run = self._candidate(candidate_id)
            if not run['config'].get('cards'):
                raise ValueError('Candidate validation requires declared screenshot matrix')
            with tempfile.TemporaryDirectory(dir=self.paths.workspace, prefix='validation-') as temporary:
                directory = Path(temporary)
                media, recipe, closure = self._materialize(candidate, directory)
                cfg = recipe / 'creative.config.json'; cfg.write_bytes(canonical(run['config']))
                errors = []
                expected = set(validator.declared_screenshots(run['config']))
                if run['config'].get('previewVideo', {}).get('enabled'):
                    expected.add('preview/app_preview.mp4')
                    if any(closure[item]['role'] == 'poster' for item in candidate['artifacts']):
                        expected.add('preview/poster.png')
                selected = {closure[item]['logical_path'] for item in candidate['artifacts']}
                for unexpected in sorted(selected - expected):
                    errors.append(f'Output not declared in release matrix: {unexpected}')
                for identity in candidate['artifacts']:
                    record = closure[identity]
                    if not record['inputs']:
                        errors.append(f'Missing source provenance: {record["logical_path"]}')
                with contextlib.redirect_stdout(io.StringIO()):
                    probe = validator.run_validation(recipe, cfg, media, write_lockfile=False)
                errors.extend(probe['errors'])
                # Recheck producer bytes after inspecting the materialized copy.
                self._closure(candidate['artifacts'])
                return self._record('validations', {'id': identifier(), 'candidate_id': candidate_id,
                    'candidate_sha256': hashlib.sha256(canonical(candidate)).hexdigest(),
                    'run_id': run['id'], 'config_sha256': run['config_sha256'],
                    'policy_version': 'media-v1', 'status': 'FAIL' if errors else 'PASS',
                    'errors': errors, 'assets': probe['assets'], 'source_hashes': probe['source_hashes']})

    def _validated(self, candidate_id, validation_id):
        from artifact_lifecycle import canonical
        import hashlib
        candidate, run = self._candidate(candidate_id)
        validation = self._read('validations', validation_id)
        if (validation['candidate_id'] != candidate_id or validation['status'] != 'PASS'
                or validation['candidate_sha256'] != hashlib.sha256(canonical(candidate)).hexdigest()
                or validation['config_sha256'] != run['config_sha256']):
            raise ValueError('Passing validation is not bound to candidate')
        self._closure(candidate['artifacts'])
        return candidate, run, validation

    def approve_design(self, candidate_id, validation_id, actor, authorization_reference):
        from artifact_lifecycle import identifier
        if not actor or not authorization_reference:
            raise ValueError('Explicit human actor and authorization reference are required')
        with self.transaction():
            candidate, run, validation = self._validated(candidate_id, validation_id)
            return self._record('approvals', {'id': identifier(), 'stage': 'design', 'actor': actor,
                'authorization_reference': authorization_reference, 'candidate_id': candidate_id,
                'candidate_sha256': validation['candidate_sha256'], 'validation_id': validation_id,
                'config_sha256': run['config_sha256']})

    def seal(self, candidate_id, validation_id, approval_id, parent_revision=None):
        from artifact_lifecycle import canonical, digest, identifier, safe_id
        with self.transaction():
            candidate, run, validation = self._validated(candidate_id, validation_id)
            approval = self._read('approvals', approval_id)
            if (approval.get('stage') != 'design' or approval['candidate_id'] != candidate_id
                    or approval['validation_id'] != validation_id
                    or approval['candidate_sha256'] != validation['candidate_sha256']):
                raise ValueError('Design approval is not bound to candidate validation')
            if parent_revision:
                parent = self._read('deliveries', parent_revision)
                if parent['project_id'] != run['config']['project']['id'] or parent['target'] != run['target']:
                    raise ValueError('Parent revision belongs to a different release')
            target = run['target']; project = safe_id(run['config']['project']['id'])
            platform = safe_id(target['platform']); version = relative_name(target['version'])
            if '/' in version:
                raise ValueError('Version must be one portable path component')
            revision = identifier(); parent_dir = self.paths.releases / project / platform / version
            parent_dir.mkdir(parents=True, exist_ok=True)
            destination = parent_dir / revision
            with tempfile.TemporaryDirectory(dir=parent_dir, prefix='.sealing-') as temporary:
                staged = Path(temporary); media, recipe_inputs, closure = self._materialize(candidate, staged)
                # Separate recipe configuration from the inputs it references.
                recipe_inputs.rename(staged / 'inputs-staging')
                (staged / 'recipe').mkdir(); (staged / 'inputs-staging').rename(staged / 'recipe' / 'inputs')
                config = json.loads(canonical(run['config'])); config.pop('storage', None)
                input_names = {data['logical_path'] for identity, data in closure.items()
                               if identity not in candidate['artifacts'] and data['role'] != 'render-evidence'}
                def rewrite(value):
                    if isinstance(value, dict):
                        return {key: ('inputs/' + item.lstrip('/') if key in ('screenshot', 'source', 'imageUrl')
                                     and isinstance(item, str) and item.lstrip('/') in input_names else rewrite(item))
                                for key, item in value.items()}
                    if isinstance(value, list):
                        return [rewrite(item) for item in value]
                    return value
                config = rewrite(config)
                (staged / 'recipe' / 'config.json').write_bytes(canonical(config))
                evidence = staged / 'evidence'; evidence.mkdir()
                for name, data in (('candidate', candidate), ('validation', validation), ('design-approval', approval)):
                    (evidence / f'{name}.json').write_bytes(canonical(data))
                artifacts = [{'artifact_id': identity, 'path': 'media/' + closure[identity]['logical_path'],
                              'role': closure[identity]['role'], 'sha256': closure[identity]['sha256']}
                             for identity in candidate['artifacts']]
                inputs = [{'artifact_id': identity, 'path': 'recipe/inputs/' + data['logical_path'], 'sha256': data['sha256']}
                          for identity, data in closure.items()
                          if identity not in candidate['artifacts'] and data['role'] != 'render-evidence']
                files = [{'path': path.relative_to(staged).as_posix(), 'sha256': digest(path), 'size_bytes': path.stat().st_size}
                         for path in sorted(staged.rglob('*')) if path.is_file()]
                manifest = {'schema_version': 1, 'revision_id': revision, 'project_id': project,
                            'target': target, 'parent_revision': parent_revision,
                            'candidate_sha256': validation['candidate_sha256'], 'assets': artifacts,
                            'recipe_inputs': inputs, 'files': files}
                (staged / 'manifest.json').write_bytes(canonical(manifest))
                result = verify_archive(staged)
                # Destination has a new identity and is never updated in place.
                commit_directory(staged, destination)
                staged.mkdir()
            return self._record('deliveries', {'id': revision, 'candidate_id': candidate_id,
                'validation_id': validation_id, 'approval_id': approval_id, 'project_id': project,
                'target': target, 'parent_revision': parent_revision,
                'manifest_sha256': result['manifest_sha256'], 'local_path': str(destination),
                'storage': self.paths.binding(),
                'package_verified': True, 'recipe_verified': True})
