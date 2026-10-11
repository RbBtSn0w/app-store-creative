"""Immutable metadata bundles hydrate original delivery manifests exactly."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from artifact_lifecycle import canonical
from configuration_layers import _read_regular, _document
from delivery_lifecycle import verify_archive, relative_name, commit_directory
from external_media_store import FileSystemMediaStore
from inventory_lifecycle import files_without_links


def _location(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('External archive location must be absolute without aliases')
    return path


def externalize(package, destination, backend, backend_root, expected_manifest_sha256):
    package = _location(package); destination = _location(destination)
    verify_archive(package, expected_manifest_sha256)
    from archive_policy import require_retrieval
    require_retrieval(json.loads((package / 'recipe/config.json').read_text()),
                      {'media_mode': 'external', 'backend': backend})
    if destination.exists() or destination.is_symlink():
        raise ValueError('External metadata destination already exists')
    store = FileSystemMediaStore(backend, backend_root)
    manifest = _document(_read_regular(package / 'manifest.json'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.external-archive-') as directory:
        staged = Path(directory); metadata = staged / 'archive'; metadata.mkdir()
        objects = []
        for item in manifest['files']:
            name = relative_name(item['path']); source = package / name
            if name.startswith(('media/', 'recipe/inputs/')):
                reference = store.persist(source)
                if reference['sha256'] != item['sha256'] or reference['size_bytes'] != item['size_bytes']:
                    raise ValueError('External archive source integrity changed')
                objects.append({'path': name, 'reference': reference})
            else:
                target = metadata / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        shutil.copyfile(package / 'manifest.json', metadata / 'manifest.json')
        descriptor = {'schema_version': 1, 'kind': 'external-delivery-archive', 'backend': backend,
                      'manifest_sha256': expected_manifest_sha256, 'objects': objects}
        payload = canonical(descriptor); (staged / 'external.json').write_bytes(payload)
        descriptor_sha = hashlib.sha256(payload).hexdigest()
        # Test the metadata and backend as an independent consumer before publishing.
        with tempfile.TemporaryDirectory(prefix='creative-external-archive-readback-') as check:
            restore_external(staged, Path(check).resolve() / 'package', backend, backend_root, descriptor_sha)
        commit_directory(staged, destination); staged.mkdir()
    return {'metadata_path': str(destination), 'descriptor_sha256': descriptor_sha,
            'manifest_sha256': expected_manifest_sha256, 'retrieval_verified': True,
            'external_objects': len(objects), 'remote_write': False}


def restore_external(bundle, destination, backend, backend_root, expected_descriptor_sha256):
    bundle = _location(bundle); destination = _location(destination)
    payload = _read_regular(bundle / 'external.json')
    if hashlib.sha256(payload).hexdigest() != expected_descriptor_sha256:
        raise ValueError('External archive descriptor integrity differs')
    descriptor = _document(payload)
    if (set(descriptor) != {'schema_version', 'kind', 'backend', 'manifest_sha256', 'objects'}
            or type(descriptor['schema_version']) is not int or descriptor['schema_version'] != 1
            or descriptor['kind'] != 'external-delivery-archive' or descriptor['backend'] != backend
            or not isinstance(descriptor['objects'], list)):
        raise ValueError('Invalid external archive descriptor')
    store = FileSystemMediaStore(backend, backend_root)
    manifest_payload = _read_regular(bundle / 'archive/manifest.json')
    if hashlib.sha256(manifest_payload).hexdigest() != descriptor['manifest_sha256']:
        raise ValueError('External archive manifest integrity differs')
    manifest = _document(manifest_payload)
    if not isinstance(manifest.get('files'), list):
        raise ValueError('Invalid external archive file manifest')
    declared = {}
    for item in manifest['files']:
        if not isinstance(item, dict): raise ValueError('Invalid external archive file record')
        name = relative_name(item.get('path'))
        if name in declared or name == 'manifest.json': raise ValueError('Duplicate external archive path')
        declared[name] = item
    references = {}
    for item in descriptor['objects']:
        if not isinstance(item, dict) or set(item) != {'path', 'reference'}:
            raise ValueError('Invalid external archive object binding')
        name = relative_name(item['path']); reference = item['reference']; store.object_path(reference)
        if (name in references or name not in declared or not name.startswith(('media/', 'recipe/inputs/'))
                or reference['sha256'] != declared[name].get('sha256')
                or reference['size_bytes'] != declared[name].get('size_bytes')):
            raise ValueError('External archive object coverage or integrity differs')
        references[name] = reference
    required = {name for name in declared if name.startswith(('media/', 'recipe/inputs/'))}
    if set(references) != required:
        raise ValueError('External archive object coverage is incomplete')
    files, links = files_without_links(bundle, strict=True)
    actual = {path.relative_to(bundle).as_posix() for path in files}
    expected = {'external.json', 'archive/manifest.json'} | {'archive/' + name for name in declared if name not in references}
    if links or actual != expected:
        raise ValueError('External metadata archive has unexpected files or links')
    if destination.exists() or destination.is_symlink():
        raise ValueError('External archive restore destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.external-restore-') as directory:
        staged = Path(directory)
        for name in declared:
            target = staged / name; target.parent.mkdir(parents=True, exist_ok=True)
            if name in references: store.retrieve(references[name], target)
            else: shutil.copyfile(bundle / 'archive' / name, target)
        (staged / 'manifest.json').write_bytes(manifest_payload)
        result = verify_archive(staged, descriptor['manifest_sha256'])
        commit_directory(staged, destination); staged.mkdir()
    return {**result, 'descriptor_sha256': expected_descriptor_sha256, 'external_retrieval_verified': True,
            'restored_path': str(destination), 'remote_write': False}


def export_managed(core, delivery_id, backend, backend_root):
    from artifact_lifecycle import identifier
    from external_media_store import managed_store
    with core.transaction():
        backend_root = managed_store(core, backend, backend_root).root
        delivery = core._read('deliveries', delivery_id)
        package = core.delivery_path(delivery)
        identity = identifier()
        destination = core.paths.publications / 'external-archives' / identity
        result = externalize(package, destination, backend, backend_root, delivery['manifest_sha256'])
        return core._record('external-archives', {'id': identity, 'delivery_id': delivery_id,
            'backend': backend, **result})


def verify_external_git(root, commit, archive_path, expected_descriptor_sha256, backend, backend_root, remote=None, destination=None):
    """Verify metadata from the selected commit and hydrate its exact object versions."""
    import os
    import re
    from delivery_lifecycle import RetrievalCommands
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        raise ValueError('External archive retrieval requires a full commit identity')
    relative = relative_name(archive_path)
    if not isinstance(expected_descriptor_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_descriptor_sha256):
        raise ValueError('External retrieval requires a trusted descriptor hash')
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment.update(GIT_LFS_SKIP_SMUDGE='1', GIT_TERMINAL_PROMPT='0')
    commands = RetrievalCommands(environment)
    git = shutil.which('git')
    if not git:
        raise ValueError('Git tooling unavailable for external archive retrieval')
    source = str(_location(root))
    if remote is not None:
        if not isinstance(remote, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', remote):
            raise ValueError('External retrieval requires a configured remote name')
        configured = commands.run([git, '-C', source, 'remote', 'get-url', remote], timeout=30)
        if configured.returncode:
            raise ValueError('External retrieval remote is not configured')
        source = configured.stdout.strip()
        if not (source.startswith(('https://', 'ssh://', 'file://', '/'))
                or re.fullmatch(r'[A-Za-z0-9_.@-]+:[^:\s][^\s]*', source)):
            raise ValueError('External retrieval remote transport is unsupported')
    with tempfile.TemporaryDirectory(prefix='creative-external-git-') as directory:
        checkout = Path(directory).resolve() / 'checkout'
        for args in (['clone', '--no-local', '--no-checkout', '--', source, str(checkout)],
                     ['-C', str(checkout), 'checkout', '--detach', commit]):
            completed = commands.run([git, '-c', 'core.hooksPath=/dev/null', *args])
            if completed.returncode:
                raise ValueError('Independent external metadata retrieval failed')
        restored = restore_external(checkout / relative, _location(destination) if destination is not None else Path(directory).resolve() / 'package', backend,
                                    backend_root, expected_descriptor_sha256)
        return {'retrieval_verified': True, 'package_verified': restored['package_verified'],
                'recipe_verified': restored['recipe_verified'], 'provenance_verified': restored['provenance_verified'],
                'media_mode': 'external', 'backend': backend, 'descriptor_sha256': expected_descriptor_sha256,
                'manifest_sha256': restored['manifest_sha256'], 'archive_commit': commit, 'archive_path': relative,
                'source_scope': 'configured-remote' if remote else 'local-repository', 'remote_name': remote,
                'proof': 'Independent commit checkout and complete external object retrieval; no producer workspace fallback'}
