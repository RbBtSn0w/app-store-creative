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


def _effective_previews(config, locales=None):
    """Return the merged previewVideo declarations enabled for the selected locales."""
    global_pv = config.get('previewVideo', {})
    global_enabled = global_pv.get('enabled', False)
    localizations = config.get('localizations', {})
    has_locale_previews = isinstance(localizations, dict) and any(
        isinstance(l_cfg, dict) and 'previewVideo' in l_cfg for l_cfg in localizations.values()
    )
    effective_pvs = []
    if has_locale_previews:
        project_locales = config.get('project', {}).get('locales', [])
        all_locales = set(project_locales)
        if isinstance(localizations, dict):
            all_locales.update(localizations.keys())
        if locales is not None:
            all_locales = all_locales.intersection(set(locales))
        for loc in all_locales:
            l_cfg = localizations.get(loc, {}) if isinstance(localizations, dict) else {}
            l_pv = l_cfg.get('previewVideo', {}) if isinstance(l_cfg, dict) else {}
            merged = {**global_pv, **l_pv}
            if merged.get('enabled', global_enabled):
                effective_pvs.append(merged)
    elif global_enabled:
        effective_pvs.append(global_pv)
    return effective_pvs


def produce(root, config_path=None, targets=None, locales=None, with_video=False,
            progress=None, expected_revision=None, experiment_provenance=None,
            require_declared_video=False):
    root = Path(root).resolve(); cfg = Path(config_path or root / 'creative.config.json').resolve()
    core = Lifecycle.from_configuration(root, cfg)
    raw = core._configuration_layers.project_bytes
    if expected_revision is not None and expected_revision != '"' + core._configuration_layers.revision + '"':
        raise ValueError('Project changed after review; save and export again')
    config = contract.check_config(core.config)
    effective_pvs = _effective_previews(config, locales)
    if require_declared_video and effective_pvs and not with_video:
        raise ValueError('creative.config.json enables previewVideo; rerun export with --with-video '
                         '(or set previewVideo.enabled to false) so the declared preview is produced')
    if with_video:
        from managed_poster import timestamp_from_time_code
        for epv in effective_pvs:
            if epv.get('posterRequired'):
                timestamp_from_time_code(epv.get('posterFrameTimeCode'), epv.get('fps', 30))
    publishing = config.get('publishing', {})
    platform = publishing.get('platform') or ('MAC_OS' if all(t.startswith('mac_') for t in config.get('targets', [])) else 'IOS')
    sources, input_errors = contract.input_hashes(root, config, targets, locales)
    if with_video:
        pv_sources = []
        for epv in effective_pvs:
            if epv.get('source'):
                pv_sources.append(epv['source'])
            if epv.get('audioSource') or epv.get('audio_source'):
                pv_sources.append(epv.get('audioSource') or epv.get('audio_source'))

        if effective_pvs and not pv_sources:
            input_errors.append('Preview source must be a managed local regular file')
        for src in set(pv_sources):
            name = relative_name(src)
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
                artifact = core.register(attempt['id'], path, 'source', logical_path=name,
                                         inputs=parents, experiment_provenance=experiment_provenance)
                if artifact['sha256'] != sha:
                    raise ValueError('Source changed while preparing production')
                destination = input_root / name; destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(core.object_path(artifact['sha256']), destination)
                source_ids.append(artifact['id']); original_hashes[name] = sha
            # Text-only compositions still bind their output to the reviewed recipe.
            recipe = json.loads(canonical(config)); recipe.pop('storage', None)
            recipe_source = work / 'reviewed-recipe.json'; recipe_source.write_bytes(canonical(recipe))
            recipe_artifact = core.register(attempt['id'], recipe_source, 'source',
                                            logical_path='reviewed-recipe.json',
                                            experiment_provenance=experiment_provenance)
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
                video = video_engine.produce_preview_from_config(input_root, input_cfg, output_dir=outputs, locales=locales)
            core._live_configuration()
            if cfg.read_bytes() != raw or any(digest(contract.local_asset(root, name, config)) != sha for name, sha in original_hashes.items()):
                raise ValueError('Inputs changed during production; review the current project and retry')
            selected = []
            evidence = outputs / '.export-evidence.json'
            evidence_id = None
            if evidence.is_file():
                evidence_id = core.register(attempt['id'], evidence, 'render-evidence', inputs=source_ids,
                                            logical_path='.export-evidence.json',
                                            experiment_provenance=experiment_provenance)['id']
            dependencies = source_ids + ([evidence_id] if evidence_id else [])
            for output in result['artifacts']:
                selected.append(core.register(attempt['id'], Path(output['path']), 'screenshot',
                                              inputs=dependencies, logical_path=output['name'],
                                              experiment_provenance=experiment_provenance)['id'])
            if video:
                from managed_preview import portable_receipt
                video_items = video['videos'].values() if 'videos' in video else [video]
                for v in video_items:
                    preview_path = Path(v['path'])
                    receipt_path = Path(v['receipt_path'])
                    frames_path = Path(v['frames_path'])
                    logical_preview = v.get('logical_path', 'preview/app_preview.mp4')
                    preview_dir = Path(logical_preview).parent.as_posix()
                    evidence_prefix = f'evidence/{preview_dir}' if preview_dir != 'preview' else 'evidence'
                    logical_receipt = f'{evidence_prefix}/preview-receipt.json'
                    logical_frames = f'{evidence_prefix}/preview-frames.png'
                    video_outputs = [(preview_path, 'preview', logical_preview),
                                     (receipt_path, 'producer-evidence', logical_receipt),
                                     (frames_path, 'producer-evidence', logical_frames)]
                    receipt_path.write_bytes(canonical(portable_receipt(
                        json.loads(receipt_path.read_bytes()), input_root, video_outputs, input_prefix='')))
                    frames = core.register(attempt['id'], frames_path, 'producer-evidence', inputs=source_ids,
                                           logical_path=logical_frames,
                                           experiment_provenance=experiment_provenance)
                    receipt = core.register(attempt['id'], receipt_path, 'producer-evidence',
                                            inputs=source_ids + [frames['id']], logical_path=logical_receipt,
                                            experiment_provenance=experiment_provenance)
                    selected.append(core.register(attempt['id'], preview_path, 'preview',
                                                  inputs=source_ids + [receipt['id']],
                                                  logical_path=logical_preview,
                                                  experiment_provenance=experiment_provenance)['id'])
        core.finish_attempt(attempt['id'], 'succeeded')
        if with_video:
            from managed_poster import produce as produce_poster, timestamp_from_time_code
            preview_ids = [item for item in selected if core._read('artifacts', item)['role'] == 'preview']
            has_posters = False
            for p_id in preview_ids:
                art = core._read('artifacts', p_id)
                log_path = art.get('logical_path', '')
                parts = log_path.split('/')
                target_cfg = dict(config.get('previewVideo', {}))
                if len(parts) == 3 and parts[1] == 'preview':
                    locale_key = parts[0]
                    target_cfg.update(config.get('localizations', {}).get(locale_key, {}).get('previewVideo', {}))
                if target_cfg.get('enabled') and target_cfg.get('posterRequired'):
                    ts = timestamp_from_time_code(target_cfg.get('posterFrameTimeCode'), target_cfg.get('fps', 30))
                    poster = produce_poster(core, run['id'], p_id, ts, 'creative-producer')
                    selected.append(poster['poster_artifact_id'])
                    has_posters = True
            if has_posters:
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
                              inputs=source_ids, logical_path='diagnostics/export-failure.json',
                              experiment_provenance=experiment_provenance)
            except Exception as diagnostic_error:
                error.add_note('Could not register export diagnostic: ' + str(diagnostic_error))
            for path, role, logical in (
                    (outputs / 'preview/app_preview.mp4', 'preview', 'preview/app_preview.mp4'),
                    (outputs / 'preview/app_preview.frames.png', 'producer-evidence', 'evidence/preview-frames.png')):
                try:
                    if path.is_file():
                        core.register(attempt['id'], path, role, partial=True,
                                      inputs=source_ids, logical_path=logical,
                                      experiment_provenance=experiment_provenance)
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
