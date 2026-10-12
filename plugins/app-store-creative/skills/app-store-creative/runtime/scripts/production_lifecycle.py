"""Shared production orchestration for CLI and Studio."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

from artifact_lifecycle import Lifecycle, canonical, digest
from delivery_lifecycle import relative_name
import export_engine
import studio_contract as contract
import video_engine


def produce(root, config_path=None, targets=None, locales=None, with_video=False,
            progress=None, expected_revision=None):
    root = Path(root).resolve(); cfg = Path(config_path or root / 'creative.config.json').resolve()
    core = Lifecycle.from_configuration(root, cfg)
    raw = core._configuration_layers.project_bytes
    if expected_revision is not None and expected_revision != '"' + core._configuration_layers.revision + '"':
        raise ValueError('Project changed after review; save and export again')
    config = contract.check_config(core.config)
    poster_timestamp = None
    if with_video and config.get('previewVideo', {}).get('enabled') and config['previewVideo'].get('posterRequired'):
        from managed_poster import timestamp_from_time_code
        poster_timestamp = timestamp_from_time_code(config['previewVideo'].get('posterFrameTimeCode'),
                                                   config['previewVideo'].get('fps', 30))
    publishing = config.get('publishing', {})
    platform = publishing.get('platform') or ('MAC_OS' if all(t.startswith('mac_') for t in config.get('targets', [])) else 'IOS')
    sources, input_errors = contract.input_hashes(root, config, targets, locales)
    if with_video and config.get('previewVideo', {}).get('enabled'):
        name = relative_name(config['previewVideo'].get('source', ''))
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            input_errors.append('Preview source must be a managed local regular file')
        else:
            sources[name] = digest(path)
    run = core.start_run({'platform': platform, 'version': publishing.get('version') or 'draft'}, source_hashes=sources)
    attempt = core.start_attempt(run['id'], 'export', 'creative-producer')
    work = core.work_path(attempt['id']); input_root = work / 'inputs'; outputs = work / 'outputs'
    source_ids = []; original_hashes = {}
    try:
        input_root.mkdir(); outputs.mkdir()
        with core.keep_lease(attempt['id']):
            if input_errors:
                raise ValueError('; '.join(input_errors))
            from input_lifecycle import imported_identity, write_snapshot_index
            for name, sha in sources.items():
                path = contract.local_asset(root, name, config)
                parents = [core.resolve_import(name)[0]['artifact_id']] if imported_identity(name) else []
                artifact = core.register(attempt['id'], path, 'source', logical_path=name, inputs=parents)
                if artifact['sha256'] != sha:
                    raise ValueError('Source changed while preparing production')
                destination = input_root / name; destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(core.object_path(artifact['sha256']), destination)
                source_ids.append(artifact['id']); original_hashes[name] = sha
            # Text-only compositions still bind their output to the reviewed recipe.
            recipe = json.loads(canonical(config)); recipe.pop('storage', None)
            recipe_source = work / 'reviewed-recipe.json'; recipe_source.write_bytes(canonical(recipe))
            recipe_artifact = core.register(attempt['id'], recipe_source, 'source', logical_path='reviewed-recipe.json')
            source_ids.append(recipe_artifact['id'])
            (input_root / 'reviewed-recipe.json').write_bytes(recipe_source.read_bytes())
            write_snapshot_index(input_root, sources)
            input_cfg = input_root / 'creative.config.json'; input_cfg.write_bytes(canonical(config))
            result = export_engine.run_export(input_root, input_cfg, output_dir=outputs,
                                             targets=targets, locales=locales, progress=progress)
            if result.get('status') != 'PASS':
                raise ValueError('; '.join(result.get('errors', [])) or 'Rendering failed')
            video = None
            if with_video:
                video = video_engine.produce_preview_from_config(input_root, input_cfg, output_dir=outputs)
            core._live_configuration()
            if cfg.read_bytes() != raw or any(digest(contract.local_asset(root, name, config)) != sha for name, sha in original_hashes.items()):
                raise ValueError('Inputs changed during production; review the current project and retry')
            selected = []
            evidence = outputs / '.export-evidence.json'
            evidence_id = None
            if evidence.is_file():
                evidence_id = core.register(attempt['id'], evidence, 'render-evidence', inputs=source_ids,
                                            logical_path='.export-evidence.json')['id']
            dependencies = source_ids + ([evidence_id] if evidence_id else [])
            for output in result['artifacts']:
                selected.append(core.register(attempt['id'], Path(output['path']), 'screenshot',
                                              inputs=dependencies, logical_path=output['name'])['id'])
            if video:
                from managed_preview import portable_receipt
                preview_path = Path(video['path'])
                receipt_path = Path(video['receipt_path'])
                frames_path = Path(video['frames_path'])
                video_outputs = [(preview_path, 'preview', 'preview/app_preview.mp4'),
                                 (receipt_path, 'producer-evidence', 'evidence/preview-receipt.json'),
                                 (frames_path, 'producer-evidence', 'evidence/preview-frames.png')]
                receipt_path.write_bytes(canonical(portable_receipt(
                    json.loads(receipt_path.read_bytes()), input_root, video_outputs, input_prefix='')))
                frames = core.register(attempt['id'], frames_path, 'producer-evidence', inputs=source_ids,
                                       logical_path='evidence/preview-frames.png')
                receipt = core.register(attempt['id'], receipt_path, 'producer-evidence',
                                        inputs=source_ids + [frames['id']], logical_path='evidence/preview-receipt.json')
                selected.append(core.register(attempt['id'], preview_path, 'preview',
                                              inputs=source_ids + [receipt['id']],
                                              logical_path='preview/app_preview.mp4')['id'])
        core.finish_attempt(attempt['id'], 'succeeded')
        if poster_timestamp is not None:
            from managed_poster import produce as produce_poster
            poster = produce_poster(core, run['id'], selected[-1], poster_timestamp, 'creative-producer')
            selected.append(poster['poster_artifact_id'])
            core._live_configuration()
            if cfg.read_bytes() != raw or any(digest(contract.local_asset(root, name, config)) != sha
                                             for name, sha in original_hashes.items()):
                raise ValueError('Inputs changed during poster production; review and retry')
        candidate = core.select(run['id'], selected)
        validation = core.validate_candidate(candidate['id'])
        return {'status': validation['status'], 'run_id': run['id'], 'attempt_id': attempt['id'],
                'candidate_id': candidate['id'], 'validation': validation, 'export': result,
                'artifacts_dir': str(outputs), 'remote_write': False}
    except BaseException as error:
        outcome = core._path('attempts', attempt['id'], 'outcome')
        if not outcome.exists():
            terminal = ('cancelled' if isinstance(error, KeyboardInterrupt) else
                        'interrupted' if isinstance(error, SystemExit) else 'failed')
            try:
                diagnostic_path = work / 'export-failure.json'
                diagnostic_path.write_bytes(canonical({'schema_version': 1, 'run_id': run['id'],
                    'attempt_id': attempt['id'], 'stage': 'export', 'status': terminal,
                    'failure_type': type(error).__name__}))
                core.register(attempt['id'], diagnostic_path, 'diagnostic', partial=True,
                              inputs=source_ids, logical_path='diagnostics/export-failure.json')
            except Exception as diagnostic_error:
                error.add_note('Could not register export diagnostic: ' + str(diagnostic_error))
            for path, role, logical in (
                    (outputs / 'preview/app_preview.mp4', 'preview', 'preview/app_preview.mp4'),
                    (outputs / 'preview/app_preview.frames.png', 'producer-evidence', 'evidence/preview-frames.png')):
                try:
                    if path.is_file():
                        core.register(attempt['id'], path, role, partial=True,
                                      inputs=source_ids, logical_path=logical)
                except Exception as partial_error:
                    error.add_note('Could not register partial export: ' + str(partial_error))
            try:
                core.finish_attempt(attempt['id'], terminal,
                                    reason=str(error) or type(error).__name__)
            except ValueError as lease_error:
                error.add_note('Outcome could not be committed: ' + str(lease_error))
        raise


def latest(root, config_path=None):
    """Read the current candidate without writing new validations on every poll."""
    import hashlib
    root = Path(root).resolve(); cfg = Path(config_path or root / 'creative.config.json').resolve()
    core = Lifecycle.from_configuration(root, cfg)
    from artifact_lifecycle import configuration_identity
    wanted = configuration_identity(core.config)
    candidates = []
    for path in (core.paths.workspace / 'records/candidates').glob('*.json'):
        candidate = core._read('candidates', path.stem)
        if core._path('candidate-dispositions', candidate['id']).exists():
            continue
        run = core._run(candidate['run_id'])
        if run['config_sha256'] == wanted:
            candidates.append(candidate)
    if not candidates:
        return {'candidate_id': None, 'validation': None, 'remote_verified': False}
    candidate = max(candidates, key=lambda item: item['created_at'])
    validations = [core._read('validations', p.stem)
                   for p in (core.paths.workspace / 'records/validations').glob('*.json')]
    validation = max((item for item in validations if item['candidate_id'] == candidate['id']),
                     key=lambda item: item['created_at'], default=None)
    if validation:
        try:
            core._candidate(candidate['id'])
        except ValueError as error:
            validation = {**validation, 'status': 'STALE', 'errors': [str(error)]}
    return {'candidate_id': candidate['id'], 'run_id': candidate['run_id'],
            'validation': validation, 'remote_verified': False}
