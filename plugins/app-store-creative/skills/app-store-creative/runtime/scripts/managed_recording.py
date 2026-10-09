"""Register bounded native window recording through the shared lifecycle."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from artifact_lifecycle import canonical, digest
from recording_adapters import macos_recording_plan, validate_recording_probe, validate_execution_identity
from delivery_lifecycle import relative_name


def run_recorder(plan, output, receipt):
    script = Path(__file__).with_name('record_app_window.py')
    subprocess.run([sys.executable,str(script),'--bundle-id',plan['bundle_id'],
        '--window-id',str(plan['window_id']),'--duration',str(plan['duration']),
        '--width',str(plan['width']),'--height',str(plan['height']),'--fps',str(plan['fps']),
        '--output',str(output),'--receipt',str(receipt),'--execute'],
        stdout=sys.stderr,stderr=sys.stderr,check=True,timeout=plan['duration']+120)


def record(core, run_id, bundle_id, window_id, duration, width, height, fps, logical_path, owner):
    logical_path=relative_name(logical_path)
    if Path(logical_path).suffix.lower() != '.mov':
        raise ValueError('Managed recording requires a .mov logical path')
    macos_recording_plan(bundle_id=bundle_id,window_id=window_id,output=Path('take.mov'),
                         duration=duration,width=width,height=height,fps=fps)
    attempt=core.start_attempt(run_id,'capture-video',owner)
    work=Path(attempt['work_path']); output=work/'take.mov'; receipt=work/'native-receipt.json'
    plan=macos_recording_plan(bundle_id=bundle_id,window_id=window_id,output=output,
                             duration=duration,width=width,height=height,fps=fps)
    try:
        with core.keep_lease(attempt['id']):
            run_recorder(plan,output,receipt)
            raw=json.loads(receipt.read_text())
            if raw['plan'] != plan or raw['output']['sha256'] != digest(output):
                raise ValueError('Native recording receipt is not bound to output and plan')
            native_output = output.with_name(output.stem + '.native.mov')
            normalization = raw['normalization']
            if (raw['native_output']['sha256'] != digest(native_output)
                    or normalization['native_sha256'] != digest(native_output)
                    or normalization['output_sha256'] != digest(output)):
                raise ValueError('Normalization is not bound to native and normalized bytes')
            from recording_adapters import validate_native_recording_probe, validate_normalization_tools
            validate_native_recording_probe(plan, normalization['native_probe'])
            native_artifact = core.register(attempt['id'], native_output, 'capture',
                logical_path=str(Path(logical_path).with_suffix('.native.mov')))
            native_probe = json.loads(canonical(normalization['native_probe']))
            native_probe.get('format', {}).pop('filename', None)
            portable_normalization = {'native_sha256': normalization['native_sha256'],
                'output_sha256': normalization['output_sha256'], 'native_probe': native_probe,
                'tools': validate_normalization_tools(normalization['tools']),
                'command_sha256': hashlib.sha256(canonical(normalization['command'])).hexdigest()}
            execution_identity = validate_execution_identity(raw.get('execution_identity'))
            validate_recording_probe(plan, raw['output']['probe'])
            portable_path='recipe/inputs/'+logical_path
            probe=json.loads(canonical(raw['output']['probe']))
            if 'filename' in probe.get('format',{}):
                probe['format']['filename']=portable_path
            portable_plan={**plan,'output':portable_path}
            evidence_path=work/'portable-receipt.json'
            evidence_path.write_bytes(canonical({'schema_version':1,'kind':'managed-window-recording',
                'plan':portable_plan,'recorder_source_sha256':raw['recorder_source_sha256'],
                'execution_identity':execution_identity, 'normalization':portable_normalization,
                'execution_command_sha256':hashlib.sha256(canonical({'command':raw['command'],
                    'compile_command':raw['compile_command']})).hexdigest(),
                'output':{'path':portable_path,'sha256':raw['output']['sha256'],'probe':probe},
                'uploaded':False}))
            evidence=core.register(attempt['id'],evidence_path,'producer-evidence',
                logical_path='evidence/'+Path(logical_path).name+'.recording.json', inputs=[native_artifact['id']])
            capture=core.register(attempt['id'],output,'capture',inputs=[evidence['id']],logical_path=logical_path)
            core.finish_attempt(attempt['id'],'succeeded')
            return {'run_id':run_id,'attempt_id':attempt['id'],'status':'succeeded',
                    'capture_artifact_id':capture['id'],'evidence_artifact_id':evidence['id'],'approval_granted':False}
    except BaseException as error:
        try:
            native_output = output.with_name(output.stem + '.native.mov')
            if native_output.is_file():
                core.register(attempt['id'],native_output,'capture',partial=True,
                    logical_path=str(Path(logical_path).with_suffix('.native.mov')))
            if output.is_file():
                core.register(attempt['id'],output,'capture',partial=True,logical_path=logical_path)
            core.finish_attempt(attempt['id'],'cancelled' if isinstance(error,KeyboardInterrupt) else 'failed',str(error) or type(error).__name__)
        except Exception as evidence_error:
            error.add_note('Could not finish recording evidence: '+str(evidence_error))
        raise
