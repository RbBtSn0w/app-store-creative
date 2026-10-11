"""Recording adapter registers real executor evidence without UI test side effects."""
import hashlib
import json
from unittest.mock import patch
import unittest
import test_artifact_lifecycle as fixtures


def fixture_execution_identity():
    return {'compiler': {'name': 'swiftc', 'version': 'fixture-test', 'executable_sha256': 'a' * 64,
                         'sdk_version': '0.0', 'target': 'arm64-apple-macosx15.0'},
            'recorder_executable_sha256': 'b' * 64,
            'probe_tools': [{'name': 'ffprobe', 'version': 'fixture-test', 'executable_sha256': 'c' * 64}],
            'environment': {'os': 'fixture', 'os_version': 'fixture', 'architecture': 'fixture'}}


class ManagedRecordingTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def test_capture_and_portable_receipt_are_linked(self):
        from managed_recording import record
        run = self.store.start_run({})
        def recorder(plan, output, receipt):
            output.write_bytes(b'recording fixture')
            native = output.with_name(output.stem + '.native.mov'); native.write_bytes(b'native fixture')
            native_sha = hashlib.sha256(native.read_bytes()).hexdigest()
            output_sha = hashlib.sha256(output.read_bytes()).hexdigest()
            native_probe = {'format': {'filename':str(native),'duration':'15'}, 'streams':[{
                'codec_type':'video','codec_name':'h264','width':1920,'height':1080,'avg_frame_rate':'24/1'}]}
            receipt.write_text(json.dumps({'plan':plan,'command':['/tmp/helper'],
                'execution_identity':fixture_execution_identity(),
                'native_output':{'path':str(native),'sha256':native_sha},
                'normalization':{'native_sha256':native_sha,'output_sha256':output_sha,
                    'native_probe':native_probe,'command':['/tmp/ffmpeg','-i',str(native),str(output)],
                    'tools':[{'name':'ffmpeg','version':'fixture-test','executable_sha256':'d'*64},
                             {'name':'ffprobe','version':'fixture-test','executable_sha256':'c'*64}]},
                'compile_command':['xcrun','swiftc','/tmp/source.swift'], 'recorder_source_sha256':'a'*64,
                'output':{'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                    'probe':{'format':{'filename':str(output),'duration':'15'}, 'streams':[{'codec_type':'video','codec_name':'h264','width':1920,'height':1080,'avg_frame_rate':'30/1'}]}}}))
        with patch('managed_recording.run_recorder', side_effect=recorder):
            result = record(self.store,run['id'],'test.app.dev',42,15,1920,1080,30,'sources/take.mov','agent')
        capture = self.store.verify_artifact(result['capture_artifact_id'])
        self.assertEqual(capture['role'],'capture'); self.assertEqual(len(capture['inputs']),1)
        evidence = self.store.verify_artifact(capture['inputs'][0])
        data = self.store.object_path(evidence['sha256']).read_text()
        self.assertNotIn(str(self.root),data); self.assertNotIn('/tmp/helper',data)
        self.assertEqual(len(evidence['inputs']), 1)
        native = self.store.verify_artifact(evidence['inputs'][0])
        self.assertTrue(native['logical_path'].endswith('.native.mov'))
        self.assertEqual(self.store.object_path(native['sha256']).read_bytes(), b'native fixture')

    def test_recording_failure_preserves_partial_capture_and_reason(self):
        from managed_recording import record
        run = self.store.start_run({})
        def recorder(plan, output, receipt):
            output.write_bytes(b'partial'); raise ValueError('Screen capture unavailable')
        with patch('managed_recording.run_recorder', side_effect=recorder):
            with self.assertRaisesRegex(ValueError,'Screen capture unavailable'):
                record(self.store,run['id'],'test.app.dev',42,15,1920,1080,30,'sources/take.mov','agent')
        self.assertEqual(self.store.status(run['id'])['attempts'][0]['outcome']['status'],'failed')
        artifacts=[self.store._read('artifacts',path.stem) for path in (self.store.paths.workspace/'records/artifacts').glob('*.json')]
        self.assertTrue(any(item['partial'] and item['role']=='capture' for item in artifacts))

    def test_failed_normalization_keeps_native_take_as_partial(self):
        from managed_recording import record
        run = self.store.start_run({})
        def recorder(plan, output, receipt):
            output.with_name(output.stem + '.native.mov').write_bytes(b'native acquisition')
            raise ValueError('Normalization failed')
        with patch('managed_recording.run_recorder', side_effect=recorder):
            with self.assertRaisesRegex(ValueError, 'Normalization failed'):
                record(self.store,run['id'],'test.app.dev',42,15,1920,1080,30,
                       'sources/take.mov','agent')
        artifacts = [self.store._read('artifacts', path.stem) for path in
                     (self.store.paths.workspace/'records/artifacts').glob('*.json')]
        native = next(a for a in artifacts if a['logical_path'] == 'sources/take.native.mov')
        self.assertTrue(native['partial'])
        self.assertEqual(self.store.object_path(native['sha256']).read_bytes(), b'native acquisition')
        self.assertEqual(self.store.status(run['id'])['attempts'][0]['outcome']['status'], 'failed')
