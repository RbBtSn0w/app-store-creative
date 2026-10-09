"""Lease native preview execution and register its immutable artifact closure."""
import json
from pathlib import Path
import shutil
from artifact_lifecycle import canonical


def portable_receipt(data, inputs, outputs, input_prefix="sources/"):
    """Keep exact hashes/probes while replacing local executor path bindings."""
    mapping = {str(path): 'recipe/inputs/' + input_prefix + path.relative_to(inputs).as_posix()
               for path in inputs.rglob('*') if path.is_file()}
    for path, role, logical in outputs:
        mapping[str(path)] = ('media/' if role == 'preview' else 'recipe/inputs/') + logical
    for field, index in [('execution_command', 0), ('snapshot_command', 2)]:
        command = data.get(field)
        if isinstance(command, list) and command:
            mapping[str(command[-1])] = mapping[str(outputs[index][0])]
    def visit(value):
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        if isinstance(value, list):
            return [visit(item) for item in value]
        if isinstance(value, str):
            if value in mapping:
                return mapping[value]
            if Path(value).is_absolute():
                if Path(value).name in ('ffmpeg', 'ffprobe'):
                    return Path(value).name
                raise ValueError('Preview receipt contains an unbound absolute path')
        return value
    return visit(data)


def produce(core, run_id, contract_path, logical_path, owner):
    import produce_app_preview
    from delivery_lifecycle import relative_name
    logical_path = relative_name(logical_path)
    contract_path = Path(contract_path).resolve()
    contract = json.loads(contract_path.read_text())
    attempt = core.start_attempt(run_id, 'preview', owner)
    work = Path(attempt['work_path']); inputs = work / 'inputs'; inputs.mkdir()
    dependencies = []
    portable = json.loads(canonical(contract))
    outputs = [(work / 'preview.mp4', 'preview', logical_path),
               (work / 'receipt.json', 'producer-evidence', 'evidence/preview-receipt.json'),
               (work / 'frames.png', 'producer-evidence', 'evidence/preview-frames.png')]
    try:
        with core.keep_lease(attempt['id']):
            items = [*portable.get('segments', []), *portable.get('overlays', []), portable.get('end_card') or {}]
            for index, item in enumerate(items):
                if 'path' in item and 'artifact_id' in item:
                    raise ValueError('Timeline input must declare either path or artifact_id')
                parents = []
                if 'artifact_id' in item:
                    original = core.verify_artifact(item['artifact_id'])
                    outcome_path = core._path('attempts', original['attempt_id'], 'outcome')
                    if (original['partial'] or original['role'] != 'capture' or not outcome_path.exists()
                            or core._read('attempts', original['attempt_id'], 'outcome')['status'] != 'succeeded'):
                        raise ValueError('Timeline input requires a completed capture artifact')
                    source = core.object_path(original['sha256'])
                    suffix = Path(original['name']).suffix.lower()
                    parents = [original['id']]
                    del item['artifact_id']
                elif 'path' in item:
                    source = Path(item['path'])
                    source = source if source.is_absolute() else contract_path.parent / source
                    suffix = source.suffix.lower()
                else:
                    continue
                name = 'input-' + str(index) + suffix
                snapshot = inputs / name
                shutil.copyfile(source, snapshot)
                artifact = core.register(attempt['id'], snapshot, 'capture', inputs=parents,
                                         logical_path='sources/' + name)
                dependencies.append(artifact['id'])
                # Execute the registered bytes even if an external source changed during capture.
                shutil.copyfile(core.object_path(artifact['sha256']), snapshot)
                item['path'] = name
            recipe_path = inputs / 'timeline.json'; recipe_path.write_bytes(canonical(portable))
            recipe = core.register(attempt['id'], recipe_path, 'source', inputs=dependencies,
                                   logical_path='sources/timeline.json')
            dependencies.append(recipe['id'])
            execution = json.loads(canonical(portable))
            for item in [*execution.get('segments', []), *execution.get('overlays', []), execution.get('end_card') or {}]:
                if 'path' in item:
                    item['path'] = str(inputs / item['path'])
            produce_app_preview.execute(execution, *(path for path, _, _ in outputs))
            receipt_path = outputs[1][0]
            receipt_path.write_bytes(canonical(portable_receipt(json.loads(receipt_path.read_text()), inputs, outputs)))
            frames = core.register(attempt['id'], outputs[2][0], outputs[2][1],
                                   inputs=dependencies, logical_path=outputs[2][2])
            evidence = core.register(attempt['id'], receipt_path, outputs[1][1],
                                     inputs=dependencies + [frames['id']], logical_path=outputs[1][2])
            preview = core.register(attempt['id'], outputs[0][0], 'preview',
                                    inputs=dependencies + [evidence['id']], logical_path=logical_path)
            registered = [preview, evidence, frames]
            core.finish_attempt(attempt['id'], 'succeeded')
            return {'run_id': run_id, 'attempt_id': attempt['id'], 'status': 'succeeded',
                    'preview_artifact_id': registered[0]['id'],
                    'artifact_ids': [item['id'] for item in registered], 'approval_granted': False}
    except BaseException as error:
        try:
            for path, role, logical in outputs:
                if path.is_file():
                    core.register(attempt['id'], path, role, partial=True, inputs=dependencies, logical_path=logical)
            core.finish_attempt(attempt['id'], 'cancelled' if isinstance(error, KeyboardInterrupt) else 'failed', str(error) or type(error).__name__)
        except Exception as evidence_error:
            error.add_note('Could not finish managed preview evidence: ' + str(evidence_error))
        raise
