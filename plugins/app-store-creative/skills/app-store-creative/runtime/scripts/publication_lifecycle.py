"""Local ASC handoffs bound to immutable archives and actual Git commits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


def check_remote_target(target, delivery, config=None):
    if (not isinstance(target, dict)
            or any(not isinstance(target.get(key), str) or not target[key].strip()
                   for key in ('app_id', 'version_id', 'platform'))):
        raise ValueError('Explicit ASC app, version resource and platform are required')
    if not isinstance(target.get('bundle_id'), str) or not target['bundle_id'].strip():
        raise ValueError('Remote target requires explicit bundle_id')
    if target['platform'] != delivery['target']['platform']:
        raise ValueError('Remote platform does not match the approved delivery')
    expected_bundle_id = None
    if config and isinstance(config, dict):
        expected_bundle_id = config.get('project', {}).get('bundleId')
    if not expected_bundle_id and isinstance(delivery, dict):
        if isinstance(delivery.get('config'), dict):
            expected_bundle_id = delivery['config'].get('project', {}).get('bundleId')
        elif delivery.get('local_path'):
            recipe_cfg = Path(delivery['local_path']) / 'recipe' / 'config.json'
            if recipe_cfg.is_file():
                try:
                    expected_bundle_id = json.loads(recipe_cfg.read_text()).get('project', {}).get('bundleId')
                except Exception:
                    pass
    if expected_bundle_id and target['bundle_id'] != expected_bundle_id:
        raise ValueError('Remote target bundle identifier does not match configuration')


def publication_assets(manifest, config, package=None, prefix=''):
    assets = []
    for asset in manifest['assets']:
        metadata = {key: asset[key] for key in ('path', 'artifact_id', 'role', 'sha256')}
        metadata['path'] = prefix + asset['path']
        if package is not None:
            with (package / asset['path']).open('rb') as stream:
                metadata['source_checksum'] = hashlib.file_digest(stream, 'md5').hexdigest()
        if asset['role'] == 'preview':
            time_code = config.get('previewVideo', {}).get('posterFrameTimeCode')
            for locale, l_cfg in config.get('localizations', {}).items():
                if isinstance(l_cfg, dict) and f'/{locale}/' in f"/{asset['path']}":
                    if isinstance(l_cfg.get('previewVideo'), dict) and 'posterFrameTimeCode' in l_cfg['previewVideo']:
                        time_code = l_cfg['previewVideo']['posterFrameTimeCode']
            metadata['poster_frame_time_code'] = time_code
        assets.append(metadata)
    return assets


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
            pointer = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?', data)
            if (not pointer or pointer[1].decode() != record['sha256']
                    or int(pointer[2]) != record['size_bytes']):
                raise ValueError('Git LFS pointer differs from sealed archive manifest')
            continue
        if len(data) != record['size_bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Git archive media or recipe integrity failure')
    return relative


class PublicationOperations:
    def list_publications(self, limit=20, cursor=None):
        selected, cursor = self._record_page('publications', limit, cursor, 'plan')
        return {'publications': [{key: record[key] for key in
                ('id', 'created_at', 'delivery_id', 'target', 'archive_commit')}
                for record in selected], 'next_cursor': cursor}

    def _require_retrieval_proof(self, plan):
        proof = plan.get('retrieval_proof')
        from archive_policy import require_retrieval
        require_retrieval({'archivePolicy': plan.get('archive_policy')}, proof)
        if (not isinstance(proof, dict) or proof.get('retrieval_verified') is not True
                or proof.get('package_verified') is not True or proof.get('recipe_verified') is not True
                or proof.get('provenance_verified') is not True
                or proof.get('media_mode') not in ('git', 'lfs', 'external', 'local')):
            raise ValueError('Publication retrieval proof is missing or mismatched')
        if proof.get('media_mode') in ('git', 'lfs'):
            if ((proof.get('media_mode') == 'lfs' and not plan.get('archive_remote'))
                    or proof.get('remote_name') != plan.get('archive_remote')
                    or proof.get('source_scope') != ('configured-remote' if plan.get('archive_remote') else 'local-repository')
                    or any(proof.get(key) != plan.get(key) for key in ('archive_commit', 'archive_path', 'manifest_sha256'))):
                raise ValueError('Publication retrieval proof is missing or mismatched')
        elif proof.get('media_mode') == 'local':
            if any(proof.get(key) != plan.get(key) for key in ('archive_commit', 'archive_path', 'manifest_sha256')):
                raise ValueError('Publication retrieval proof is missing or mismatched')
        elif proof.get('media_mode') == 'external' and (
                proof.get('descriptor_sha256') != plan.get('descriptor_sha256')
                or proof.get('backend') != plan.get('backend')
                or proof.get('provenance_verified') is not True):
            raise ValueError('External publication retrieval proof is mismatched')

    def _archive_repository(self, name=None):
        if name is None:
            return self.paths.project
        from configuration_layers import load
        layers = load(self.paths.project, self.config_path)
        repository = (layers.local_config or {}).get('archiveRepositories', {}).get(name)
        if repository is None:
            raise ValueError('Named archive repository has no host-local access configuration')
        root = Path(repository['root'])
        if root.resolve() != root or not root.is_dir():
            raise ValueError('Archive repository is missing or symlinked')
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if result.returncode or Path(result.stdout.strip()).resolve() != root:
            raise ValueError('Archive repository must be an explicit Git worktree root')
        return root

    def _generate_local_delivery(self, publication_id, delivery_id, target, manifest, package):
        import shutil
        from artifact_lifecycle import now, digest
        local_dir = self.paths.publications / publication_id / 'local_delivery'
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        receipt = {
            'schema_version': 1,
            'publication_id': publication_id,
            'delivery_id': delivery_id,
            'manifest_sha256': manifest.get('manifest_sha256') or digest(package / 'manifest.json'),
            'verified_at': now(),
            'status': 'PASS',
            'target': target,
            'media_mode': 'local',
            'assets_count': len(manifest.get('assets', [])),
            'files_verified': True,
            'offline_validation': {
                'package_verified': True,
                'recipe_verified': True,
                'provenance_verified': True,
            }
        }
        (local_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        for asset in manifest.get('assets', []):
            rel_path = asset['path']
            src = package / rel_path
            dst = local_dir / rel_path
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        return local_dir

    def plan_publication(self, delivery_id, archive_commit=None, remote_target=None, archive_remote=None,
                         *, archive_repository=None, archive_path=None, local_delivery=False):
        from artifact_lifecycle import canonical, identifier
        from delivery_lifecycle import verify_archive
        with self.transaction():
            delivery = self._read('deliveries', delivery_id)
            package = self.delivery_path(delivery)
            verify_archive(package, delivery['manifest_sha256'])
            manifest = json.loads((package / 'manifest.json').read_text())
            config = json.loads((package / 'recipe/config.json').read_text())
            check_remote_target(remote_target, delivery, config)
            del_policy = delivery.get('archive_policy') or config.get('archivePolicy') or {}
            is_local = (
                local_delivery is True
                or del_policy.get('mediaMode') == 'local'
                or archive_commit == 'local'
                or (archive_commit is None and del_policy.get('mediaMode') == 'local')
            )
            if not is_local:
                if not archive_commit:
                    raise ValueError('Archive commit is required for git/lfs publication')
                repository = self._archive_repository(archive_repository)
                if archive_repository is not None:
                    if archive_path is None:
                        raise ValueError('Named archive repository requires an explicit archive path')
                    relative = committed_archive(repository, package, archive_commit, manifest, archive_path)
                else:
                    if archive_path is not None:
                        raise ValueError('Explicit archive path requires a named archive repository')
                    original = Path(delivery['local_path'])
                    if not original.is_relative_to(self.paths.project):
                        raise ValueError('Original Git archive location must be inside the repository')
                    relative = committed_archive(repository, package, archive_commit, manifest,
                                                 original.relative_to(self.paths.project).as_posix())
                from delivery_lifecycle import verify_git_archive
                retrieval = verify_git_archive(repository, archive_commit, relative, delivery['manifest_sha256'], archive_remote)
                from archive_policy import require_retrieval
                archive_policy = require_retrieval(config, retrieval)
                if delivery.get('archive_policy') != archive_policy:
                    raise ValueError('Delivery archive policy differs from retrieved recipe')
            else:
                commit_id = archive_commit if (isinstance(archive_commit, str) and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', archive_commit)) else 'local'
                original = Path(delivery['local_path'])
                relative = original.relative_to(self.paths.project).as_posix() if original.is_relative_to(self.paths.project) else str(original)
                archive_policy = {'schema_version': 1, 'mediaMode': 'local'}
                retrieval = {
                    **verify_archive(package, delivery['manifest_sha256']),
                    'retrieval_verified': True,
                    'archive_commit': commit_id,
                    'archive_path': relative,
                    'media_mode': 'local',
                    'manifest_sha256': delivery['manifest_sha256'],
                    'source_scope': 'local-filesystem',
                    'remote_name': None,
                    'proof': 'Local sealed delivery package verified on disk without Git tracking'
                }
                from archive_policy import require_retrieval
                require_retrieval(config, retrieval)
                archive_commit = commit_id

            rel_prefix = relative + '/' if relative and not relative.endswith('/') else relative
            assets = publication_assets(manifest, config, package, rel_prefix)
            identity = identifier()
            body = {'id': identity, 'delivery_id': delivery_id, 'target': remote_target,
                    'archive_commit': archive_commit, 'archive_remote': archive_remote, 'manifest_sha256': delivery['manifest_sha256'],
                    'archive_policy': archive_policy,
                    'archive_path': relative, 'retrieval_proof': retrieval, 'assets': assets, 'executor': 'official-asc-plugin',
                    'remote_write': False, 'required_actions': ['Resolve and confirm version localization resources',
                        'Obtain explicit upload approval for this plan hash', 'Execute through the official ASC plugin',
                        'Record processing, media and poster observations separately'],
                    'idempotency_key': hashlib.sha256(canonical({'delivery': delivery['manifest_sha256'], 'target': remote_target})).hexdigest()}
            if archive_repository is not None:
                body['archive_repository'] = archive_repository
            result = self._record('publications', body, 'plan')
            if is_local:
                self._generate_local_delivery(identity, delivery_id, remote_target, manifest, package)
            return result

    def _verify_publication_archive(self, plan):
        from delivery_lifecycle import verify_archive, check_delivery_manifest
        self._require_retrieval_proof(plan)
        delivery = self._read('deliveries', plan['delivery_id'])
        if plan.get('archive_policy') != delivery.get('archive_policy'):
            raise ValueError('Publication archive policy differs from sealed delivery')
        check_remote_target(plan.get('target'), delivery)
        package = None
        if delivery['manifest_sha256'] != plan['manifest_sha256']:
            raise ValueError('Publication manifest differs from approved delivery')
        if plan['retrieval_proof']['media_mode'] == 'external':
            saved = self._read('external-archives', plan['external_archive_id'])
            if (saved['delivery_id'] != delivery['id'] or saved['backend'] != plan['backend']
                    or saved['descriptor_sha256'] != plan['descriptor_sha256']
                    or saved['manifest_sha256'] != plan['manifest_sha256']):
                raise ValueError('External archive identity differs from publication plan')
            result = subprocess.run(['git', '-C', str(self.paths.project), 'show',
                plan['archive_commit'] + ':' + plan['archive_path'] + '/external.json'], capture_output=True)
            if result.returncode or hashlib.sha256(result.stdout).hexdigest() != plan['descriptor_sha256']:
                raise ValueError('Committed external descriptor differs from approved archive')
            manifest_result = subprocess.run(['git', '-C', str(self.paths.project), 'show',
                plan['archive_commit'] + ':' + plan['archive_path'] + '/archive/manifest.json'], capture_output=True)
            if (manifest_result.returncode
                    or hashlib.sha256(manifest_result.stdout).hexdigest() != delivery['manifest_sha256']):
                raise ValueError('Committed external manifest differs from approved archive')
            manifest = json.loads(manifest_result.stdout)
            check_delivery_manifest(manifest, delivery)
            config_result = subprocess.run(['git', '-C', str(self.paths.project), 'show',
                plan['archive_commit'] + ':' + plan['archive_path'] + '/archive/recipe/config.json'], capture_output=True)
            config_record = next((item for item in manifest['files'] if item['path'] == 'recipe/config.json'), None)
            if (config_result.returncode or not config_record
                    or hashlib.sha256(config_result.stdout).hexdigest() != config_record['sha256']):
                raise ValueError('Committed external recipe differs from sealed archive')
            config = json.loads(config_result.stdout)
            expected_assets = publication_assets(manifest, config)
            actual_assets = plan.get('assets')
            if (not isinstance(actual_assets, list) or any(not isinstance(asset, dict)
                    or not isinstance(asset.get('source_checksum'), str)
                    or not re.fullmatch('[0-9a-f]{32}', asset['source_checksum']) for asset in actual_assets)
                    or [{key: value for key, value in asset.items() if key != 'source_checksum'}
                        for asset in actual_assets] != expected_assets):
                raise ValueError('External publication assets differ from sealed archive')
        elif plan['retrieval_proof']['media_mode'] == 'local':
            package = self.delivery_path(delivery)
            verify_archive(package, plan['manifest_sha256'])
            manifest = json.loads((package / 'manifest.json').read_text())
            config = json.loads((package / 'recipe/config.json').read_text())
            rel_prefix = plan['archive_path'] + '/' if plan['archive_path'] and not plan['archive_path'].endswith('/') else plan['archive_path']
            expected_assets = publication_assets(manifest, config, package, rel_prefix)
            if plan.get('assets') != expected_assets:
                raise ValueError('Publication assets differ from sealed archive')
        else:
            package = self.delivery_path(delivery)
            verify_archive(package, plan['manifest_sha256'])
            manifest = json.loads((package / 'manifest.json').read_text())
            committed_archive(self._archive_repository(plan.get('archive_repository')), package, plan['archive_commit'],
                              manifest, plan['archive_path'])
            config = json.loads((package / 'recipe/config.json').read_text())
            expected_assets = publication_assets(manifest, config, package, plan['archive_path'] + '/')
            if plan.get('assets') != expected_assets:
                raise ValueError('Publication assets differ from sealed archive')
        return package

    def plan_external_publication(self, external_archive_id, archive_commit, archive_path,
                                  remote_target, backend_root, archive_remote=None):
        from artifact_lifecycle import canonical, identifier
        from delivery_lifecycle import relative_name
        from external_delivery_archive import verify_external_git
        with self.transaction():
            saved = self._read('external-archives', external_archive_id)
            from external_media_store import managed_store
            backend_root = managed_store(self, saved['backend'], backend_root).root
            delivery = self._read('deliveries', saved['delivery_id'])
            relative = relative_name(archive_path)
            import tempfile
            with tempfile.TemporaryDirectory(prefix='creative-external-plan-') as directory:
                package = Path(directory).resolve() / 'package'
                retrieval = verify_external_git(self.paths.project, archive_commit, relative,
                    saved['descriptor_sha256'], saved['backend'], backend_root, archive_remote, package)
                if retrieval['manifest_sha256'] != delivery['manifest_sha256']:
                    raise ValueError('Retrieved external archive differs from approved delivery')
                manifest = json.loads((package / 'manifest.json').read_text())
                from delivery_lifecycle import check_delivery_manifest
                check_delivery_manifest(manifest, delivery)
                config = json.loads((package / 'recipe/config.json').read_text())
                check_remote_target(remote_target, delivery, config)
                from archive_policy import require_retrieval
                archive_policy = require_retrieval(config, retrieval)
                if delivery.get('archive_policy') != archive_policy:
                    raise ValueError('Delivery archive policy differs from retrieved recipe')
                assets = publication_assets(manifest, config, package)
            body = {'id': identifier(), 'delivery_id': delivery['id'], 'target': remote_target,
                'archive_policy': archive_policy,
                'external_archive_id': external_archive_id, 'backend': saved['backend'],
                'descriptor_sha256': saved['descriptor_sha256'], 'archive_commit': archive_commit,
                'archive_remote': archive_remote, 'manifest_sha256': delivery['manifest_sha256'],
                'archive_path': relative, 'retrieval_proof': retrieval, 'assets': assets,
                'asset_path_base': 'hydrated-package', 'executor': 'official-asc-plugin', 'remote_write': False,
                'required_actions': ['Materialize the exact committed external archive before resolving asset paths',
                    'Resolve and confirm version localization resources', 'Obtain explicit upload approval for this plan hash',
                    'Execute through the official ASC plugin', 'Record processing, media and poster observations separately'],
                'idempotency_key': hashlib.sha256(canonical({'delivery': delivery['manifest_sha256'], 'target': remote_target})).hexdigest()}
            self._verify_publication_archive(body)
            return self._record('publications', body, 'plan')

    def _check_prepared_checksums(self, plan, package):
        import os
        import stat
        for asset in plan['assets']:
            path = package / asset['path']
            before = path.lstat()
            if path.resolve() != path or not stat.S_ISREG(before.st_mode):
                raise ValueError('Prepared media must be a regular file without symlinks')
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, 'rb') as stream:
                opened = os.fstat(stream.fileno())
                if (not stat.S_ISREG(opened.st_mode)
                        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)):
                    raise ValueError('Prepared media identity changed')
                sha = hashlib.sha256()
                checksum = hashlib.md5()
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    sha.update(chunk)
                    checksum.update(chunk)
                after = os.fstat(stream.fileno())
            fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if (any(getattr(opened, key) != getattr(after, key) for key in fields)
                    or sha.hexdigest() != asset['sha256']
                    or checksum.hexdigest() != asset['source_checksum']):
                raise ValueError('Prepared external media checksum differs from approved plan')

    def prepare_external_publication(self, publication_id, backend_root, destination):
        from artifact_lifecycle import canonical
        from external_delivery_archive import verify_external_git
        with self.transaction():
            plan = self._read('publications', publication_id, 'plan')
            self._verify_publication_archive(plan)
            if plan['retrieval_proof']['media_mode'] != 'external':
                raise ValueError('External preparation requires an external publication plan')
            plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
            approvals = [self._read('approvals', path.stem)
                for path in (self.paths.workspace / 'records/approvals').glob('*.json')]
            if not any(self._upload_approval_matches(item, plan, plan_hash) for item in approvals):
                raise ValueError('Explicit upload approval for this exact plan is required')
            from external_media_store import managed_store
            backend_root = managed_store(self, plan['backend'], backend_root).root
            proof = verify_external_git(self.paths.project, plan['archive_commit'], plan['archive_path'],
                plan['descriptor_sha256'], plan['backend'], backend_root, plan['archive_remote'], destination)
            if proof != plan['retrieval_proof']:
                raise ValueError('Prepared external retrieval proof differs from approved plan')
            package = Path(destination)
            self._check_prepared_checksums(plan, package)
            from artifact_lifecycle import identifier
            return self._record('publication-preparations', {'id': identifier(),
                'publication_id': publication_id, 'plan_sha256': plan_hash, 'remote_write': False,
                'uploaded': False, 'executor': 'official-asc-plugin', 'retrieval_proof': proof,
                'asset_path_base': str(package),
                'assets': [{**asset, 'path': str(package / asset['path'])} for asset in plan['assets']]})

    def external_preparation_status(self, preparation_id):
        from artifact_lifecycle import safe_id
        safe_id(preparation_id)
        from artifact_lifecycle import canonical
        from delivery_lifecycle import verify_archive
        from operation_history import read_lock
        with read_lock(self):
            verified = False
            publication_id = None
            try:
                saved = self._read('publication-preparations', preparation_id)
                plan = self._read('publications', saved['publication_id'], 'plan')
                publication_id = plan['id']
                self._verify_publication_archive(plan)
                if saved['plan_sha256'] != hashlib.sha256(canonical(plan)).hexdigest():
                    raise ValueError('Preparation is bound to another plan')
                if saved['retrieval_proof'] != plan['retrieval_proof']:
                    raise ValueError('Preparation retrieval proof differs from plan')
                package = Path(saved['asset_path_base'])
                verify_archive(package, plan['manifest_sha256'])
                self._check_prepared_checksums(plan, package)
                expected = [{**asset, 'path': str(package / asset['path'])} for asset in plan['assets']]
                if saved['assets'] != expected:
                    raise ValueError('Preparation assets differ from approved plan')
                verified = True
            except (ValueError, OSError):
                pass
            return {'preparation_id': preparation_id, 'publication_id': publication_id,
                'status': 'PASS' if verified else 'FAIL', 'files_verified': verified,
                'uploaded': False, 'remote_write': False, 'remote_verified': False}

    def _upload_approval_matches(self, approval, plan, plan_hash):
        from artifact_lifecycle import require_human_authorization
        try:
            require_human_authorization(approval.get('actor'), approval.get('authorization_reference'))
        except ValueError:
            return False
        return (approval.get('stage') == 'upload' and approval.get('publication_id') == plan['id']
                and approval.get('plan_sha256') == plan_hash and approval.get('target') == plan['target'])

    def approve_upload(self, publication_id, actor, authorization_reference):
        from artifact_lifecycle import canonical, identifier
        from artifact_lifecycle import require_human_authorization
        require_human_authorization(actor, authorization_reference)
        with self.transaction():
            plan = self._read('publications', publication_id, 'plan')
            self._require_retrieval_proof(plan)
            self._verify_publication_archive(plan)
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
            self._require_retrieval_proof(plan)
            self._verify_publication_archive(plan)
            plan_hash = hashlib.sha256(canonical(plan)).hexdigest()
            approvals = ([(self._read('approvals', path.stem), [])
                          for path in (self.paths.workspace / 'records/approvals').glob('*.json')]
                         if write else self._approval_status_records())
            approved = any(not errors and self._upload_approval_matches(item, plan, plan_hash)
                           for item, errors in approvals)
            result = {'publication_id': publication_id, 'uploaded': False, 'remote_write': False,
                      'executor': 'official-asc-plugin', 'plan_sha256': plan_hash,
                      'upload_approval': 'approved' if approved else 'pending', 'handoff': plan,
                      'approval_errors': [{'id': item['id'], 'errors': errors}
                                          for item, errors in approvals if errors]}
            if write:
                # Refuse damaged observation evidence before creating any export files.
                for observation_path in (self.paths.workspace / 'records/remote-observations').glob('*.json'):
                    self._read('remote-observations', observation_path.stem)
                self._observation_evidence_exports(publication_id, plan_hash)
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
                if plan.get('archive_policy', {}).get('mediaMode') == 'local' or plan.get('retrieval_proof', {}).get('media_mode') == 'local':
                    local_dir = self.paths.publications / publication_id / 'local_delivery'
                    if not (local_dir / 'manifest.json').exists():
                        delivery = self._read('deliveries', plan['delivery_id'])
                        pkg = self.delivery_path(delivery)
                        mf = json.loads((pkg / 'manifest.json').read_text())
                        self._generate_local_delivery(publication_id, plan['delivery_id'], plan['target'], mf, pkg)
                    result['local_delivery_path'] = str(local_dir)
            return result
