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


def check_delivery_manifest(manifest, delivery):
    fields = (('revision_id', 'id'), ('project_id', 'project_id'),
              ('target', 'target'), ('parent_revision', 'parent_revision'),
              ('archive_policy', 'archive_policy'))
    if not isinstance(manifest, dict) or any(manifest.get(left) != delivery.get(right)
                                             for left, right in fields):
        raise ValueError('Delivery identity differs from sealed archive')


def verify_provenance(package, manifest, file_hashes):
    from artifact_lifecycle import safe_id
    name = 'evidence/provenance.json'
    if name not in file_hashes:
        raise ValueError('Archive provenance is missing')
    graph = json.loads((package / name).read_text())
    if (not isinstance(graph, dict) or type(graph.get('schema_version')) is not int
            or graph['schema_version'] != 1 or not isinstance(graph.get('nodes'), list)
            or graph.get('roots') != [asset['artifact_id'] for asset in manifest['assets']]):
        raise ValueError('Invalid archive provenance schema or roots')
    nodes = {}
    for node in graph['nodes']:
        if not isinstance(node, dict):
            raise ValueError('Invalid archive provenance node')
        from runtime_identity import validate
        validate(node.get('implementation'))
        identity = safe_id(node.get('id'))
        path = relative_name(node.get('path'))
        if (identity in nodes or node.get('producer_status') != 'succeeded'
                or node.get('partial') is not False or not isinstance(node.get('inputs'), list)
                or any(not isinstance(parent, str) for parent in node['inputs'])
                or len(set(node['inputs'])) != len(node['inputs'])
                or path not in file_hashes or node.get('sha256') != file_hashes[path]
                or type(node.get('size_bytes')) is not int
                or node['size_bytes'] != (package / path).stat().st_size):
            raise ValueError('Archive provenance node integrity or producer failure')
        safe_id(node.get('run_id')); safe_id(node.get('attempt_id'))
        expected_prefix = ('media/' if identity in graph['roots'] else
                           'evidence/render/' if node.get('role') == 'render-evidence' else 'recipe/inputs/')
        if not path.startswith(expected_prefix):
            raise ValueError('Archive provenance node namespace conflict')
        nodes[identity] = node
    for record in manifest['assets'] + manifest['recipe_inputs']:
        node = nodes.get(record['artifact_id'])
        if (node is None or node['path'] != record['path'] or node['sha256'] != record['sha256']
                or ('role' in record and record['role'] != node.get('role'))):
            raise ValueError('Archive provenance binding differs from manifest')
    from artifact_lifecycle import dependency_closure
    def load(identity):
        if identity not in nodes:
            raise ValueError('Archive provenance missing dependency')
        return nodes[identity]
    try:
        visited = dependency_closure(graph['roots'], load)
    except ValueError as error:
        raise ValueError('Archive provenance dependency failure: ' + str(error)) from None
    if set(visited) != set(nodes):
        raise ValueError('Archive provenance contains unrelated nodes')


def _verify_portable_recipe(config):
    if not isinstance(config, dict):
        raise ValueError('Portable recipe must be an object')
    private = {'storage', 'configuration_layers', 'project_config_snapshot'} & set(config)
    if private:
        raise ValueError('Portable recipe contains runtime storage or provenance fields: ' + ', '.join(sorted(private)))


def verify_archive(package, expected_sha256=None):
    from artifact_lifecycle import digest, safe_id
    import re
    package = Path(package).resolve()
    manifest_path = package / 'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('Archive integrity: symlinked manifest')
    sha = digest(manifest_path)
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError('Archive manifest integrity failure')
    manifest = json.loads(manifest_path.read_text())
    if (not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int
            or manifest['schema_version'] != 1
            or any(not isinstance(manifest.get(field), list) for field in ('files', 'assets', 'recipe_inputs'))
            or not manifest['files']):
        raise ValueError('Unsupported or incomplete archive manifest')
    names = set()
    file_hashes = {}
    for record in manifest['files']:
        if (not isinstance(record, dict) or type(record.get('size_bytes')) is not int
                or record['size_bytes'] < 0 or not isinstance(record.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', record['sha256'])):
            raise ValueError('Invalid archive file manifest record')
        name = relative_name(record.get('path'))
        if name in names or name == 'manifest.json':
            raise ValueError('Archive integrity: duplicate or self-referential file')
        names.add(name); file_hashes[name] = record['sha256']; path = package / name
        if (path.resolve() != path or not path.is_file()
                or path.stat().st_size != record['size_bytes'] or digest(path) != record['sha256']):
            raise ValueError(f'Archive integrity failure: {name}')
    actual = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != names | {'manifest.json'}:
        raise ValueError('Archive integrity: unexpected or missing files')
    identities = set()
    for field in ('assets', 'recipe_inputs'):
        prefix = 'media/' if field == 'assets' else 'recipe/inputs/'
        declared = set()
        for record in manifest[field]:
            if not isinstance(record, dict):
                raise ValueError('Invalid archive media or recipe binding')
            identity = safe_id(record.get('artifact_id'))
            name = relative_name(record.get('path'))
            if identity in identities or not name.startswith(prefix):
                raise ValueError('Archive binding identity or namespace conflict')
            if field == 'assets' and record.get('role') not in ('screenshot', 'preview', 'poster'):
                raise ValueError('Unsupported archive media role')
            identities.add(identity); declared.add(name)
            if name not in file_hashes or record.get('sha256') != file_hashes[name]:
                raise ValueError('Archive media or recipe hash differs from file manifest')
        auxiliary = set()
        if field == 'recipe_inputs':
            from input_lifecycle import SNAPSHOT_INDEX, imported_identity
            index_path = prefix + SNAPSHOT_INDEX
            if index_path in names:
                expected_aliases = {record['path'][len(prefix):]: record['sha256']
                                    for record in manifest[field]
                                    if imported_identity(record['path'][len(prefix):])}
                if not expected_aliases or json.loads((package / index_path).read_text()) != expected_aliases:
                    raise ValueError('Archive input snapshot index differs from source bindings')
                auxiliary.add(index_path)
        if declared | auxiliary != {name for name in names if name.startswith(prefix)}:
            raise ValueError('Archive media or recipe coverage is incomplete')
    if 'recipe/config.json' not in names or not manifest.get('assets'):
        raise ValueError('Archive recipe or media incomplete')
    evidence_records = {}
    for name in ('candidate', 'validation', 'design-approval'):
        relative = 'evidence/' + name + '.json'
        if relative not in names:
            raise ValueError('Archive approval or validation evidence is missing')
        record = json.loads((package / relative).read_text())
        if (not isinstance(record, dict) or type(record.get('schema_version')) is not int
                or record['schema_version'] != 1):
            raise ValueError('Unsupported archive approval or validation schema')
        safe_id(record.get('id'))
        evidence_records[name] = record
    candidate = evidence_records['candidate']
    validation = evidence_records['validation']
    approval = evidence_records['design-approval']
    candidate_hash = file_hashes['evidence/candidate.json']
    if (manifest.get('candidate_sha256') != candidate_hash
            or validation.get('candidate_sha256') != candidate_hash
            or validation.get('candidate_id') != candidate['id']
            or validation.get('run_id') != candidate.get('run_id')
            or validation.get('status') != 'PASS' or validation.get('errors') != []
            or validation.get('policy_version') != 'media-v1'
            or candidate.get('artifacts') != [asset['artifact_id'] for asset in manifest['assets']]):
        raise ValueError('Archive validation is not bound to selected candidate')
    config_hash = validation.get('config_sha256')
    if (not isinstance(config_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', config_hash)
            or approval.get('stage') != 'design' or approval.get('candidate_id') != candidate['id']
            or approval.get('candidate_sha256') != candidate_hash
            or approval.get('validation_id') != validation['id']
            or approval.get('config_sha256') != config_hash
            or not isinstance(approval.get('target'), dict)
            or any(not isinstance(approval['target'].get(key), str) or not approval['target'][key].strip()
                   for key in ('platform', 'version'))
            or approval.get('target') != manifest.get('target')
            or any(not isinstance(approval.get(key), str) or not approval[key].strip()
                   for key in ('actor', 'authorization_reference'))):
        raise ValueError('Archive design approval is not bound to passing validation')
    verify_provenance(package, manifest, file_hashes)
    import studio_contract
    recipe_config = json.loads((package / 'recipe/config.json').read_text())
    from archive_policy import resolve as resolve_archive_policy
    archive_policy = resolve_archive_policy(recipe_config, required=True)
    if manifest.get('archive_policy') != archive_policy:
        raise ValueError('Manifest archive policy differs from recipe declaration')
    _verify_portable_recipe(recipe_config)
    _, findings = studio_contract.input_hashes(package / 'recipe', recipe_config)
    preview = recipe_config.get('previewVideo', {})
    if preview.get('enabled'):
        source = relative_name(preview.get('source', ''))
        if 'recipe/' + source not in names:
            findings.append('Missing preview recipe source')
    if findings:
        raise ValueError('Archive recipe integrity: ' + '; '.join(findings))
    return {'package_verified': True, 'recipe_verified': True, 'provenance_verified': True, 'manifest_sha256': sha,
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


def exchange_directories(staged, destination, expected_source_identity=None, expected_destination_identity=None):
    """Swap occupied roots atomically; a sync error can occur after the swap."""
    staged, destination = Path(staged).absolute(), Path(destination).absolute()
    for path in (staged, destination):
        if path.resolve() != path or path.is_symlink() or not path.is_dir():
            raise ValueError('Directory exchange requires a regular directory without aliases')
    if staged == destination or staged.is_relative_to(destination) or destination.is_relative_to(staged):
        raise ValueError('Directory exchange requires distinct non-overlapping roots')
    identity = lambda stat: (stat.st_dev, stat.st_ino)
    before_source, before_target = staged.stat(), destination.stat()
    for expected, info in ((expected_source_identity, before_source), (expected_destination_identity, before_target)):
        if expected is not None:
            if (not isinstance(expected, list) or len(expected) != 2
                    or any(type(value) is not int or value < 0 for value in expected)
                    or expected != list(identity(info))):
                raise ValueError('Directory exchange expected identity differs')
    if before_source.st_dev != before_target.st_dev:
        raise ValueError('Atomic directory exchange requires one filesystem')
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin' and hasattr(libc, 'renameatx_np'):
        call = libc.renameatx_np
    elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
        call = libc.renameat2
    else:
        raise ValueError('Atomic directory exchange is unavailable on this platform')
    call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    call.restype = ctypes.c_int
    with contextlib.ExitStack() as cleanup:
        descriptors = []
        for path in (staged, destination):
            parent_before = path.parent.stat()
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            cleanup.callback(os.close, fd)
            if identity(os.fstat(fd)) != identity(parent_before):
                raise ValueError('Directory exchange parent changed')
            descriptors.append(fd)
        source_fd, target_fd = descriptors
        source_name, target_name = os.fsencode(staged.name), os.fsencode(destination.name)
        if (identity(os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)) != identity(before_source)
                or identity(os.stat(target_name, dir_fd=target_fd, follow_symlinks=False)) != identity(before_target)):
            raise ValueError('Directory exchange roots changed')
        # Darwin RENAME_SWAP and Linux RENAME_EXCHANGE both use flag value 2.
        if call(source_fd, source_name, target_fd, target_name, 2):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
        if (identity(os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)) != identity(before_target)
                or identity(os.stat(target_name, dir_fd=target_fd, follow_symlinks=False)) != identity(before_source)):
            raise ValueError('Directory exchange result identity differs')
        for fd in descriptors:
            os.fsync(fd)
    return {'source': str(staged), 'destination': str(destination),
            'source_identity_before': list(identity(before_source)),
            'destination_identity_before': list(identity(before_target)),
            'parent_directories_synced': True, 'source_deleted': False}


def apply_directory_change(change):
    """Apply one journaled root change or resume its completed filesystem state."""
    if not isinstance(change, dict) or change.get('operation') not in ('EXCHANGE', 'PUBLISH'):
        raise ValueError('Unknown directory change operation')
    paths = []
    for key in ('staging', 'destination'):
        value = change.get(key)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError('Directory change requires an absolute path')
        path = Path(value)
        if str(path) != value or path.resolve() != path or path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError('Directory change path is not a regular directory')
        paths.append(path)
    staged, destination = paths
    if staged == destination or staged.is_relative_to(destination) or destination.is_relative_to(staged):
        raise ValueError('Directory change roots overlap')
    def expected(key, nullable=False):
        value = change.get(key)
        if nullable and value is None:
            return None
        if not isinstance(value, list) or len(value) != 2 or any(type(item) is not int or item < 0 for item in value):
            raise ValueError('Directory change identity evidence is invalid')
        return value
    source_before = expected('staging_identity')
    target_before = expected('destination_identity', change['operation'] == 'PUBLISH')
    if change['operation'] == 'PUBLISH' and target_before is not None:
        raise ValueError('Directory publication requires an absent destination identity')
    def actual(path):
        if not path.exists():
            return None
        info = path.stat()
        return [info.st_dev, info.st_ino]
    before = (source_before, target_before)
    after = (target_before, source_before)
    current = (actual(staged), actual(destination))
    if current == before:
        if change['operation'] == 'EXCHANGE':
            exchange_directories(staged, destination, source_before, target_before)
        else:
            commit_directory(staged, destination)
        status = 'APPLIED'
    elif current == after:
        status = 'ALREADY_APPLIED'
    else:
        raise ValueError('Directory change identity differs from journaled states')
    if (actual(staged), actual(destination)) != after:
        raise ValueError('Directory change result identity differs')
    for parent in {staged.parent, destination.parent}:
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {'status': status, 'operation': change['operation'],
            'staging': str(staged), 'destination': str(destination),
            'parent_directories_synced': True, 'source_deleted': False}


def revert_directory_change(change):
    """Restore journaled directory positions without deleting either copy."""
    if not isinstance(change, dict) or change.get('operation') not in ('EXCHANGE', 'PUBLISH'):
        raise ValueError('Unknown directory change operation')
    inverse = {'operation': change['operation'],
               'staging': change.get('destination'), 'destination': change.get('staging'),
               'staging_identity': change.get('staging_identity'),
               'destination_identity': change.get('destination_identity')}
    result = apply_directory_change(inverse)
    return {**result, 'status': 'REVERTED' if result['status'] == 'APPLIED' else 'ALREADY_REVERTED',
            'staging': change['staging'], 'destination': change['destination'], 'direction': 'REVERT'}


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
        manifest = json.loads((package / 'manifest.json').read_text())
        candidate = json.loads((package / 'evidence/candidate.json').read_text())
        validation = json.loads((package / 'evidence/validation.json').read_text())
        approval = json.loads((package / 'evidence/design-approval.json').read_text())
        check_delivery_manifest(manifest, delivery)
        if (candidate['id'] != delivery.get('candidate_id')
                or validation['id'] != delivery.get('validation_id')
                or approval['id'] != delivery.get('approval_id')):
            raise ValueError('Delivery identity or approval differs from sealed archive')
        return package

    def list_deliveries(self, limit=20, cursor=None):
        selected, cursor = self._record_page('deliveries', limit, cursor)
        return {'deliveries': [{key: record[key] for key in
                ('id', 'created_at', 'project_id', 'target', 'parent_revision', 'manifest_sha256')}
                for record in selected], 'next_cursor': cursor}

    def delivery_status(self, delivery_id):
        from artifact_lifecycle import safe_id
        safe_id(delivery_id)
        delivery = None
        try:
            delivery = self._read('deliveries', delivery_id)
            package = self.delivery_path(delivery)
            verified = verify_archive(package, delivery['manifest_sha256'])
            return {'delivery_id': delivery_id, 'local_status': 'PASS', **verified,
                    'errors': [], 'remote_status': 'UNKNOWN', 'remote_write': False}
        except (ValueError, OSError) as error:
            if isinstance(error, FileNotFoundError) and delivery is None:
                raise
            return {'delivery_id': delivery_id, 'local_status': 'FAIL',
                    'package_verified': False, 'recipe_verified': False, 'provenance_verified': False,
                    'errors': [str(error)], 'remote_status': 'UNKNOWN', 'remote_write': False}

    def _candidate(self, candidate_id, *, allow_discarded=False):
        from artifact_lifecycle import configuration_identity
        candidate = self._read('candidates', candidate_id)
        if not allow_discarded and self._path('candidate-dispositions', candidate_id).exists():
            raise ValueError('Candidate is discarded; select a new candidate')
        run = self._run(candidate['run_id'])
        if (configuration_identity(self.config) != run['config_sha256']
                or configuration_identity(self._live_configuration()) != run['config_sha256']):
            raise ValueError('Candidate configuration changed; create a new run')
        from artifact_lifecycle import digest
        for name, expected in run.get('source_hashes', {}).items():
            import studio_contract
            source = studio_contract.local_asset(self.paths.project, name, run['config'])
            if not source.is_file() or digest(source) != expected:
                raise ValueError('Candidate source inputs changed; start a new run')
        for identity in candidate['artifacts']:
            self.verify_artifact(identity)
            errors = self.source_eligibility_errors(identity)
            if errors:
                raise ValueError('; '.join(errors))
        return candidate, run

    def _closure(self, identities):
        from artifact_lifecycle import dependency_closure
        return dependency_closure(identities, self.verify_artifact)

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

    def candidate_review(self, candidate_id):
        candidate, run = self._candidate(candidate_id)
        def records(category):
            values = [self._read(category, path.stem)
                      for path in (self.paths.workspace / 'records' / category).glob('*.json')]
            return sorted((item for item in values if item.get('candidate_id') == candidate_id),
                          key=lambda item: (item['created_at'], item['id']), reverse=True)
        validations = records('validations')
        approvals = [item for item in records('approvals') if item.get('stage') == 'design']
        deliveries = records('deliveries')
        delivery = deliveries[0] if deliveries else None
        approval = (self._read('approvals', delivery['approval_id']) if delivery else
                    approvals[0] if approvals else None)
        validation = (self._read('validations', approval['validation_id']) if approval else
                      validations[0] if validations else None)
        if validation and validation['status'] == 'PASS':
            self._validated(candidate_id, validation['id'])
        if approval:
            self._check_design_approval(candidate_id, run, validation, approval)
        if delivery:
            if delivery['validation_id'] != validation['id'] or delivery['approval_id'] != approval['id']:
                raise ValueError('Delivery review bindings differ')
            if self.delivery_status(delivery['id'])['local_status'] != 'PASS':
                raise ValueError('Saved delivery failed local verification; inspect delivery history')
        return {'candidate_id': candidate_id, 'validation': validation,
                'approval_id': approval['id'] if approval else None,
                'delivery_id': delivery['id'] if delivery else None, 'remote_write': False}

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
                    if (run['config']['previewVideo'].get('posterRequired', False)
                            or any(closure[item]['role'] == 'poster' for item in candidate['artifacts'])):
                        expected.add('preview/poster.png')
                selected = {closure[item]['logical_path'] for item in candidate['artifacts']}
                for missing in sorted(expected - selected):
                    errors.append(f'Missing declared output: {missing}')
                for unexpected in sorted(selected - expected):
                    errors.append(f'Output not declared in release matrix: {unexpected}')
                selected_previews = {identity for identity in candidate['artifacts']
                                     if closure[identity]['role'] == 'preview'}
                for identity in candidate['artifacts']:
                    record = closure[identity]
                    if record['role'] == 'poster':
                        bound_previews = {parent for parent in record['inputs']
                                          if closure[parent]['role'] == 'preview'}
                        if len(selected_previews) != 1 or bound_previews != selected_previews:
                            errors.append('Poster must reference the selected preview: ' + record['logical_path'])
                    if not record['inputs']:
                        errors.append(f'Missing source provenance: {record["logical_path"]}')
                with contextlib.redirect_stdout(io.StringIO()):
                    probe = validator.run_validation(recipe, cfg, media)
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
        if (validation.get('candidate_id') != candidate_id or validation.get('status') != 'PASS'
                or validation.get('policy_version') != 'media-v1'
                or validation.get('run_id') != run['id'] or validation.get('errors') != []
                or validation['candidate_sha256'] != hashlib.sha256(canonical(candidate)).hexdigest()
                or validation['config_sha256'] != run['config_sha256']):
            raise ValueError('Passing validation is not bound to candidate')
        self._closure(candidate['artifacts'])
        return candidate, run, validation

    def approve_design(self, candidate_id, validation_id, actor, authorization_reference):
        from artifact_lifecycle import identifier
        from artifact_lifecycle import require_human_authorization
        require_human_authorization(actor, authorization_reference)
        with self.transaction():
            candidate, run, validation = self._validated(candidate_id, validation_id)
            return self._record('approvals', {'id': identifier(), 'stage': 'design', 'actor': actor,
                'authorization_reference': authorization_reference, 'candidate_id': candidate_id,
                'candidate_sha256': validation['candidate_sha256'], 'validation_id': validation_id,
                'config_sha256': run['config_sha256'], 'target': run['target']})

    def _check_design_approval(self, candidate_id, run, validation, approval):
        from artifact_lifecycle import require_human_authorization
        require_human_authorization(approval.get('actor'), approval.get('authorization_reference'))
        if (approval.get('stage') != 'design' or approval.get('candidate_id') != candidate_id
                or approval.get('validation_id') != validation['id']
                or approval.get('candidate_sha256') != validation['candidate_sha256']
                or approval.get('config_sha256') != run['config_sha256']
                or approval.get('target') != run['target']):
            raise ValueError('Design approval is not bound to candidate validation')

    def seal(self, candidate_id, validation_id, approval_id, parent_revision=None):
        from artifact_lifecycle import canonical, digest, identifier, safe_id
        with self.transaction():
            candidate, run, validation = self._validated(candidate_id, validation_id)
            approval = self._read('approvals', approval_id)
            self._check_design_approval(candidate_id, run, validation, approval)
            from archive_policy import resolve as resolve_archive_policy
            archive_policy = resolve_archive_policy(run['config'], required=True)
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
                _verify_portable_recipe(config)
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
                for data in closure.values():
                    if data['role'] == 'render-evidence':
                        name = relative_name(data['logical_path'])
                        evidence_target = evidence / 'render' / name
                        evidence_target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(media / name), evidence_target)
                for name, data in (('candidate', candidate), ('validation', validation), ('design-approval', approval)):
                    (evidence / f'{name}.json').write_bytes(canonical(data))
                artifacts = [{'artifact_id': identity, 'path': 'media/' + closure[identity]['logical_path'],
                              'role': closure[identity]['role'], 'sha256': closure[identity]['sha256']}
                             for identity in candidate['artifacts']]
                inputs = [{'artifact_id': identity, 'path': 'recipe/inputs/' + data['logical_path'], 'sha256': data['sha256']}
                          for identity, data in closure.items()
                          if identity not in candidate['artifacts'] and data['role'] != 'render-evidence']
                provenance = []
                for identity, data in closure.items():
                    prefix = ('media/' if identity in candidate['artifacts'] else
                              'evidence/render/' if data['role'] == 'render-evidence' else 'recipe/inputs/')
                    outcome = self._read('attempts', data['attempt_id'], 'outcome')
                    provenance.append({key: data[key] for key in
                        ('id', 'role', 'sha256', 'size_bytes', 'inputs', 'partial', 'run_id', 'attempt_id')})
                    provenance[-1].update(path=prefix + data['logical_path'], producer_status=outcome['status'],
                        implementation=self._read('attempts', data['attempt_id'], 'started')['implementation'])
                (evidence / 'provenance.json').write_bytes(canonical({'schema_version': 1,
                    'roots': candidate['artifacts'], 'nodes': provenance}))
                files = [{'path': path.relative_to(staged).as_posix(), 'sha256': digest(path), 'size_bytes': path.stat().st_size}
                         for path in sorted(staged.rglob('*')) if path.is_file()]
                manifest = {'schema_version': 1, 'revision_id': revision, 'project_id': project,
                            'target': target, 'parent_revision': parent_revision,
                            'archive_policy': archive_policy,
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
                'archive_policy': archive_policy,
                'manifest_sha256': result['manifest_sha256'], 'local_path': str(destination),
                'storage': self.paths.binding(),
                'package_verified': True, 'recipe_verified': True})


class RetrievalCommands:
    """Bound the entire command sequence and stop its owned process group."""

    def __init__(self, environment, budget=300):
        import time
        self.environment = environment
        self.deadline = time.monotonic() + budget

    def run(self, arguments, timeout=120):
        import signal
        import subprocess
        import time
        remaining = min(timeout, self.deadline - time.monotonic())
        if remaining <= 0:
            raise ValueError('Independent Git archive retrieval timed out')
        if os.name != 'posix':
            raise ValueError('Archive retrieval requires owned process group support')
        process = subprocess.Popen(arguments, env=self.environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=remaining)
        except BaseException as failure:
            # Kill the group even if its leader has exited while a child holds a pipe.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.stdout.close()
            process.stderr.close()
            process.wait(timeout=5)
            if isinstance(failure, subprocess.TimeoutExpired):
                raise ValueError('Independent Git archive retrieval timed out') from None
            raise
        return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)


def verify_git_archive(root, commit, archive_path, expected_sha256, remote=None):
    """Prove Git-mode recovery without sharing the source repository objects."""
    import re
    import subprocess
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ValueError('Archive retrieval requires a full commit identity')
    relative = relative_name(archive_path)
    root = Path(root).resolve()
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0')
    git = '/opt/homebrew/bin/git' if Path('/opt/homebrew/bin/git').is_file() else 'git'
    commands = RetrievalCommands(environment)
    source = str(root)
    if remote is not None:
        if not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', remote):
            raise ValueError('Archive retrieval requires a configured remote name')
        resolved = commands.run([git, '-C', str(root), 'remote', 'get-url', remote], timeout=30)
        if resolved.returncode:
            raise ValueError('Archive retrieval remote is not configured')
        source = resolved.stdout.strip()
        if not (source.startswith(('https://', 'ssh://', 'file://', '/'))
                or re.fullmatch(r'[A-Za-z0-9_.@-]+:[^:\s][^\s]*', source)):
            raise ValueError('Archive retrieval remote transport is unsupported')
    with tempfile.TemporaryDirectory(prefix='creative-archive-retrieval-') as directory:
        checkout = Path(directory).resolve() / 'checkout'
        def run(arguments):
            result = commands.run([git, '-c', 'core.hooksPath=/dev/null', *arguments])
            if result.returncode:
                raise ValueError('Independent Git archive retrieval failed')
        run(['clone', '--no-local', '--no-checkout', '--', source, str(checkout)])
        run(['-C', str(checkout), 'checkout', '--detach', commit])
        package = checkout / relative
        if package.resolve() != package or not package.is_dir():
            raise ValueError('Retrieved archive location is missing or symlinked')
        media_mode = 'git'
        pointers = []
        for path in package.rglob('*'):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 1024:
                if path.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1\n'):
                    pointers.append(path)
        if pointers:
            if remote is None:
                raise ValueError('LFS retrieval requires a configured remote')
            if (checkout / '.lfsconfig').exists():
                raise ValueError('LFS retrieval refuses repository endpoint overrides')
            media_mode = 'lfs'
            run(['-C', str(checkout), 'lfs', 'version'])
            run(['-C', str(checkout), 'lfs', 'fetch', 'origin', commit])
            run(['-C', str(checkout), 'lfs', 'checkout', '--', relative])
        result = verify_archive(package, expected_sha256)
        from archive_policy import require_retrieval
        require_retrieval(json.loads((package / 'recipe/config.json').read_text()),
                          {'media_mode': media_mode})
        return {**result, 'retrieval_verified': True, 'archive_commit': commit,
                'archive_path': relative, 'media_mode': media_mode,
                'source_scope': 'configured-remote' if remote else 'local-repository', 'remote_name': remote,
                'proof': 'Independent clone with no local object sharing; detached commit checkout'}
