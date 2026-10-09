"""Synthetic media fixtures prove native archive portability, not product capture."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_artifact_lifecycle
from artifact_lifecycle import Lifecycle
from delivery_lifecycle import restore_archive, verify_archive
from test_v2_workflow import create_mock_png
from test_managed_recording import fixture_execution_identity


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Native media tools required')
class NativePreviewArchiveTests(unittest.TestCase):
    def test_sealed_recipe_replays_after_original_workspace_is_removed(self):
        self.exercise_archive(False)

    def test_registered_recording_recipe_replays_after_workspace_removal(self):
        self.exercise_archive(True)

    def exercise_archive(self, registered):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); project = root / 'project'; project.mkdir()
            take = project / 'synthetic.mp4'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                'testsrc2=size=320x180:rate=30','-t','15','-an','-c:v','libx264','-preset','ultrafast',str(take)],check=True)
            shot = project / 'fixture.png'; create_mock_png(shot,2880,1800)
            cfg = {'project':{'id':'synthetic-fixture','name':'Test Only','bundleId':'test.fixture','locales':['en-US']},
                'targets':['mac_16_10'],'cards':[{'id':'hero','screenshot':'fixture.png'}],
                'previewVideo':{'enabled':True,'posterRequired':True,'duration':15,'source':'sources/input-0.mp4','locales':['en-US']}}
            cfg['archivePolicy'] = {'schema_version': 1, 'mediaMode': 'git'}
            (project / 'creative.config.json').write_text(json.dumps(cfg))
            timeline = project / 'timeline.json'; timeline.write_text(json.dumps({'width':1920,'height':1080,
                'fps':30,'duration':15,'segments':[{'path':take.name,'duration':15,'has_audio':False}]}))
            core = Lifecycle(project,cfg); run = core.start_run({'version':'fixture','platform':'MAC_OS'})
            if registered:
                from managed_recording import record
                def recorder(plan, output, receipt):
                    from recording_normalization import normalize
                    from media_tool_identity import MediaTools
                    native = output.with_name(output.stem + '.native.mov')
                    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i',
                                    str(take), '-c', 'copy', str(native)], check=True)
                    normalization = normalize(plan, native, output, MediaTools())
                    receipt.write_text(json.dumps({'plan': plan, 'command': ['fixture-recorder'],
                        'compile_command': [], 'recorder_source_sha256': 'a' * 64,
                        'execution_identity': fixture_execution_identity(),
                        'native_output': {'path':str(native),'sha256':normalization['native_sha256']},
                        'normalization': normalization,
                        'output': {'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                                   'probe': json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(output)], check=True, capture_output=True, text=True).stdout)}}))
                with patch('managed_recording.run_recorder', side_effect=recorder):
                    recording = record(core, run['id'], 'test.fixture.dev', 42, 15,
                                       320, 180, 30, 'sources/take.mov', 'fixture-agent')
                data = json.loads(timeline.read_text())
                data['segments'][0].pop('path')
                data['segments'][0]['artifact_id'] = recording['capture_artifact_id']
                timeline.write_text(json.dumps(data))
                cfg['previewVideo']['source'] = 'sources/input-0.mov'
                (project / 'creative.config.json').write_text(json.dumps(cfg))
                # The run configuration must match the recipe selected for this fixture.
                core = Lifecycle(project, cfg)
                run = core.start_run({'version': 'fixture', 'platform': 'MAC_OS'})
            cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
            execution = subprocess.run([sys.executable, str(cli), 'preview', 'produce',
                '--repo', str(project), '--run-id', run['id'], '--contract', str(timeline),
                '--logical-path', 'preview/app_preview.mp4', '--owner', 'fixture-agent',
                '--confirm', 'EXECUTE'], capture_output=True, text=True, timeout=120)
            self.assertEqual(execution.returncode, 0, execution.stderr)
            preview = json.loads(execution.stdout)
            self.assertEqual(preview['status'], 'succeeded')
            self.assertFalse(preview['approval_granted'])
            attempt = core.start_attempt(run['id'],'fixture-screenshot','fixture-agent')
            raw = core.register(attempt['id'],shot,'capture',logical_path='fixture.png')
            output = core.register(attempt['id'],shot,'screenshot',inputs=[raw['id']],logical_path='en-US/mac_16_10/hero.png')
            core.finish_attempt(attempt['id'],'succeeded')
            poster_execution = subprocess.run([sys.executable, str(cli), 'preview', 'poster',
                '--repo', str(project), '--run-id', run['id'], '--preview-id', preview['preview_artifact_id'],
                '--timestamp', '3', '--owner', 'fixture-agent', '--confirm', 'EXTRACT'],
                capture_output=True, text=True, timeout=90)
            self.assertEqual(poster_execution.returncode, 0, poster_execution.stderr)
            poster = json.loads(poster_execution.stdout)
            candidate = core.select(run['id'],[output['id'],preview['preview_artifact_id'],poster['poster_artifact_id']])
            validation = core.validate_candidate(candidate['id']); self.assertEqual(validation['status'],'PASS',validation['errors'])
            approval = core.approve_design(candidate['id'],validation['id'],'test-human','fixture:test-approval')
            delivery = core.seal(candidate['id'],validation['id'],approval['id'])
            package = root / 'restored'; restore_archive(Path(delivery['local_path']),package,delivery['manifest_sha256'])
            shutil.rmtree(project)
            verify_archive(package,delivery['manifest_sha256'])
            frame = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams',
                '-of', 'json', str(package / 'media/preview/poster.png')], check=True,
                capture_output=True, text=True).stdout)['streams'][0]
            self.assertEqual((frame['width'], frame['height']), (1920, 1080))
            self.assertEqual(frame['codec_name'], 'png')
            poster_receipt = json.loads((package / 'recipe/inputs/evidence/poster-receipt.json').read_text())
            self.assertEqual(poster_receipt['timestamp_seconds'], 3)
            self.assertTrue((package / poster_receipt['output']).is_file())
            evidence = json.loads((package / 'recipe/inputs/evidence/preview-receipt.json').read_text())
            for tools in (evidence['tools'], poster_receipt['media']['tools']):
                self.assertEqual([item['name'] for item in tools], ['ffmpeg', 'ffprobe'])
                for item in tools:
                    self.assertTrue(item['version'])
                    self.assertRegex(item['executable_sha256'], r'^[0-9a-f]{64}$')
                self.assertNotIn(str(project), json.dumps(tools))
            self.assertNotIn(str(project),json.dumps(evidence))
            for source in evidence['sources']:
                self.assertTrue((package / source['path']).is_file())
            self.assertTrue((package / evidence['acceptance_snapshot']['path']).is_file())
            if registered:
                recording_evidence = json.loads((package / 'recipe/inputs/evidence/take.mov.recording.json').read_text())
                recovered_take = package / recording_evidence['output']['path']
                self.assertTrue(recovered_take.is_file())
                self.assertEqual(hashlib.sha256(recovered_take.read_bytes()).hexdigest(),
                                 recording_evidence['output']['sha256'])
                self.assertNotIn(str(project), json.dumps(recording_evidence))
            replay_contract = package / 'recipe/inputs/sources/timeline.json'
            recipe = json.loads(replay_contract.read_text())
            for item in recipe['segments']:
                item['path'] = str(replay_contract.parent / item['path'])
            from produce_app_preview import execute
            execute(recipe,root/'replay.mp4',root/'replay.json',root/'frames.png')
            self.assertTrue((root/'replay.mp4').is_file())
