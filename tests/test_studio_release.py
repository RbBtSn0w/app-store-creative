"""Regression coverage for the first verified screenshot workflow."""
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/scripts"))
import export_engine
import validator
import studio_contract
from test_v2_workflow import create_mock_png


class StudioReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = self.root / "creative.config.json"
        self.config = {"project": {"id": "demo", "name": "Demo", "bundleId": "com.example.demo",
                                   "locales": ["en-US", "zh-Hans"]},
                       "theme": {"background": {"type": "solid", "colors": ["#111111"]}},
                       "targets": ["iphone_6_9"], "cards": [{"id": "hero", "headline": "Real UI"}]}
        self.cfg.write_text(json.dumps(self.config))

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, ctx, path, data=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{ctx.port}{path}",
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read()), response.headers

    def test_stale_save_preserves_newer_disk_and_rejects_cross_origin(self):
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = self.request(ctx, "/api/config")
            revision = headers.get("ETag")
            self.assertIsNotNone(revision, "Studio must expose a conditional-save revision")
            updated = {**self.config, "connectedTrack": True}
            self.request(ctx, "/api/config", updated, {"If-Match": revision})
            with self.assertRaises(urllib.error.HTTPError) as conflict:
                self.request(ctx, "/api/config", self.config, {"If-Match": revision})
            self.assertEqual(conflict.exception.code, 409)
            self.assertTrue(json.loads(self.cfg.read_text())["connectedTrack"])
            with self.assertRaises(urllib.error.HTTPError) as origin:
                self.request(ctx, "/api/config", self.config, {"Origin": "https://untrusted.example"})
            self.assertEqual(origin.exception.code, 403)

    def test_import_preserves_bytes_and_duplicate_names(self):
        source = self.root / "source.png"
        create_mock_png(source, 12, 24)
        first = source.read_bytes()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            a, _ = self.request(ctx, "/api/assets", {"name": "capture.png", "data": base64.b64encode(first).decode()})
            create_mock_png(source, 16, 32)
            second = source.read_bytes()
            b, _ = self.request(ctx, "/api/assets", {"name": "capture.png", "data": base64.b64encode(second).decode()})
            self.assertNotEqual(a["path"], b["path"])
            self.assertEqual(studio_contract.local_asset(self.root, a["path"], self.config).read_bytes(), first)
            self.assertEqual(studio_contract.local_asset(self.root, b["path"], self.config).read_bytes(), second)
            with self.assertRaises(urllib.error.HTTPError) as corrupt:
                self.request(ctx, "/api/assets", {"name": "bad.png", "data": base64.b64encode(first[:40]).decode()})
            self.assertEqual(corrupt.exception.code, 400)

    def test_strict_release_cannot_verify_files_without_render_evidence(self):
        self.config["studio"] = {"requireExportEvidence": True}
        self.cfg.write_text(json.dumps(self.config))
        for locale in ("en-US", "zh-Hans"):
            create_mock_png(self.root / f"artifacts/{locale}/iphone_6_9/hero.png")
        result = validator.run_validation(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("evidence" in error.lower() for error in result["errors"]))

    def test_servers_do_not_replace_each_others_config(self):
        other = self.root / "other"
        other.mkdir()
        other_cfg = other / "creative.config.json"
        other_cfg.write_text(json.dumps({**self.config, "connectedTrack": True}))
        with export_engine.LocalServerContext(self.root, self.cfg) as first:
            with export_engine.LocalServerContext(other, other_cfg) as second:
                a, _ = self.request(first, "/api/config")
                b, _ = self.request(second, "/api/config")
                self.assertNotIn("connectedTrack", a)
                self.assertTrue(b["connectedTrack"])

    def test_renderer_rejects_screenshot_without_ready_dom(self):
        output = self.root / 'blank.png'
        def screenshot(*args, **kwargs):
            create_mock_png(output, 12, 24)
            return mock.Mock(returncode=0, stdout='<html><body>Loading</body></html>', stderr='')
        with mock.patch('export_engine.subprocess.run', side_effect=screenshot):
            self.assertFalse(export_engine.export_single_card('chrome', 3100, 'hero', 'iphone_6_9', 'en-US', output))

    def test_source_change_during_export_cannot_publish_outputs(self):
        source = self.root / 'capture.png'
        create_mock_png(source, 12, 24)
        self.config['cards'][0]['screenshot'] = '/capture.png'
        self.cfg.write_text(json.dumps(self.config))
        def render(**kwargs):
            create_mock_png(kwargs['output_path'])
            create_mock_png(source, 16, 32)
            return True
        with mock.patch('export_engine.find_chrome_binary', return_value='chrome'), mock.patch('export_engine.export_single_card', side_effect=render):
            result = export_engine.run_export(self.root)
        self.assertEqual(result['status'], 'FAIL')
        self.assertFalse((self.root / 'artifacts/en-US/iphone_6_9/hero.png').exists())

    def test_selected_export_does_not_require_unselected_locale(self):
        self.config['studio'] = {'requireExportEvidence': True}
        self.config['cards'][0]['layout'] = 'pure_text'
        self.cfg.write_text(json.dumps(self.config))
        def render(**kwargs):
            create_mock_png(kwargs['output_path'])
            return True
        with mock.patch('export_engine.find_chrome_binary', return_value='chrome'), mock.patch('export_engine.export_single_card', side_effect=render):
            result = export_engine.run_export(self.root, locales=['en-US'])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['total_rendered'], 1)
        self.assertEqual(validator.run_validation(self.root)['status'], 'FAIL')

    def test_export_rejects_changed_review_revision_before_rendering(self):
        with mock.patch('export_engine.find_chrome_binary', return_value='chrome'), mock.patch('export_engine.export_single_card') as render:
            with self.assertRaisesRegex(ValueError, 'changed'):
                export_engine.run_export(self.root, expected_revision='"stale"')
            render.assert_not_called()

    def test_invalid_nested_config_returns_actionable_client_error(self):
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', {**self.config, 'project': None})
            self.assertEqual(failure.exception.code, 400)

    def test_export_server_serves_frozen_capture_bytes(self):
        source = self.root / 'capture.png'
        create_mock_png(source, 12, 24)
        reviewed = source.read_bytes()
        with export_engine.LocalServerContext(self.root, self.cfg, asset_bytes={'capture.png': reviewed}) as ctx:
            create_mock_png(source, 16, 32)
            with urllib.request.urlopen(f'http://127.0.0.1:{ctx.port}/capture.png') as response:
                self.assertEqual(response.read(), reviewed)

    def test_matching_origin_on_foreign_host_cannot_write_project(self):
        original = self.cfg.read_bytes()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', {**self.config, 'connectedTrack': True},
                             {'Host': 'foreign.example', 'Origin': 'http://foreign.example'})
            self.assertEqual(failure.exception.code, 403)
        self.assertEqual(self.cfg.read_bytes(), original)

    def test_localized_objects_cannot_replace_text_or_crash_project_opening(self):
        original = self.cfg.read_bytes()
        invalid = {**self.config, 'localizations': {'zh-Hans': {'hero': {'headline': {'html': 'bad'}}}}}
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', invalid)
            self.assertEqual(failure.exception.code, 400)
            self.cfg.write_text(json.dumps(invalid))
            with self.assertRaises(urllib.error.HTTPError) as reading:
                self.request(ctx, '/api/config')
            self.assertEqual(reading.exception.code, 400)
            self.cfg.write_bytes(original)

    def test_validation_rejects_inputs_changed_after_evidence_check(self):
        for changed in ('config', 'source', 'output', 'symlink'):
            with self.subTest(changed=changed):
                self.config['project']['locales'] = ['en-US']
                self.config['studio'] = {'requireExportEvidence': True}
                self.config['cards'][0]['screenshot'] = '/capture.png'
                self.cfg.write_text(json.dumps(self.config))
                source = self.root / 'capture.png'
                source.unlink(missing_ok=True)
                create_mock_png(source, 12, 24)
                if changed == 'symlink':
                    source.rename(self.root / 'first.png')
                    source.symlink_to('first.png')
                    create_mock_png(self.root / 'second.png', 16, 32)
                output = self.root / 'artifacts/en-US/iphone_6_9/hero.png'
                create_mock_png(output)
                original_hash = validator.compute_sha256(self.cfg)
                sources, _ = validator.contract.input_hashes(self.root, self.config)
                (self.root / 'artifacts/.export-evidence.json').write_text(json.dumps({
                    'en-US/iphone_6_9/hero.png': {'config_hash': original_hash,
                        'source_hashes': sources, 'sha256': validator.compute_sha256(output),
                        'render_ready': True}}))
                def inspect(path):
                    if changed == 'config':
                        updated = json.loads(self.cfg.read_text())
                        updated['cards'][0]['headline'] = 'Unrendered edit'
                        self.cfg.write_text(json.dumps(updated))
                    elif changed == 'source':
                        create_mock_png(source, 16, 32)
                    elif changed == 'symlink':
                        source.unlink()
                        source.symlink_to('second.png')
                    else:
                        create_mock_png(output, 12, 24)
                    return (1320, 2868, False)
                with mock.patch.object(validator, 'read_image_meta', side_effect=inspect):
                    result = validator.run_validation(self.root)
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(result['config_hash'], original_hash)
                self.assertTrue(any('changed during validation' in error.lower() for error in result['errors']))

    def test_probe_preserves_existing_unmanaged_evidence(self):
        self.config['project']['locales'] = ['en-US']
        self.cfg.write_text(json.dumps(self.config))
        output = self.root / 'artifacts/en-US/iphone_6_9/hero.png'
        create_mock_png(output)
        existing = self.root / '.creative/release-lock.json'
        existing.parent.mkdir()
        existing.write_bytes(b'previous unmanaged evidence')
        first = validator.run_validation(self.root)
        self.assertEqual(first['status'], 'PASS')
        self.config['cards'][0]['headline'] = 'Changed copy'
        self.cfg.write_text(json.dumps(self.config))
        validator.run_validation(self.root)
        self.assertEqual(existing.read_bytes(), b'previous unmanaged evidence')
        self.assertFalse((existing.parent / 'release-history').exists())

    def test_native_browser_waits_for_complete_dom_and_pixels(self):
        profile = self.root / 'native-profile'; profile.mkdir()
        output = self.root / 'native.png'
        chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        def render(command, owned_profile, destination, timeout):
            self.assertEqual(owned_profile, profile)
            create_mock_png(destination, 12, 24)
            return mock.Mock(returncode=0, stdout='<html><body data-export-ready="true"></body></html>', stderr='')
        with mock.patch('chrome_renderer.render_native', side_effect=render), mock.patch('export_engine.stop_owned_browser') as stop:
            result = export_engine.run_native_browser([chrome, '--headless=new'], profile, output, 1)
        self.assertEqual(result.returncode, 0)
        self.assertIn('data-export-ready="true"', result.stdout)
        stop.assert_called_once_with(profile)

    def test_cleanup_never_stops_a_different_browser_profile(self):
        profile = self.root / 'owned-profile'
        own = f'101 S chrome --user-data-dir={profile}'
        other = f'202 S chrome --user-data-dir={profile}-other'
        with mock.patch('export_engine.subprocess.run', side_effect=[mock.Mock(stdout=own+'\n'+other), mock.Mock(stdout=other)]), mock.patch('export_engine.os.kill') as kill:
            export_engine.stop_owned_browser(profile)
        kill.assert_called_once_with(101, export_engine.signal.SIGTERM)



    def test_studio_poster_uses_managed_core_and_requires_current_revision(self):
        from artifact_lifecycle import Lifecycle
        core = Lifecycle(self.root, self.config, self.cfg)
        run = core.start_run({})
        attempt = core.start_attempt(run['id'], 'preview', 'fixture-agent')
        video = self.root / 'preview.mp4'; video.write_bytes(b'fixture video')
        preview = core.register(attempt['id'], video, 'preview')
        core.finish_attempt(attempt['id'], 'succeeded')
        def extract(source, output, timestamp):
            create_mock_png(output, 1920, 1080)
            return {'width':1920, 'height':1080, 'duration':15}
        payload = {'run_id':run['id'], 'preview_id':preview['id'], 'timestamp':3}
        candidate_run = core.start_run({})
        candidate_attempt = core.start_attempt(candidate_run['id'], 'render', 'fixture-agent')
        candidate_image = self.root / 'candidate.png'; create_mock_png(candidate_image, 1320, 2868)
        screenshot = core.register(candidate_attempt['id'], candidate_image, 'screenshot',
                                   logical_path='en-US/iphone_6_9/hero.png')
        core.finish_attempt(candidate_attempt['id'], 'succeeded')
        candidate = core.select(candidate_run['id'], [screenshot['id']])
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = self.request(ctx, '/api/config')
            with mock.patch('managed_poster.extract', side_effect=extract) as executor:
                with self.assertRaises(urllib.error.HTTPError) as stale:
                    self.request(ctx, '/api/preview/poster', payload, {'If-Match':'stale'})
                self.assertEqual(stale.exception.code, 409)
                executor.assert_not_called()
                result, _ = self.request(ctx, '/api/preview/poster', payload, {'If-Match':headers['ETag']})
            self.assertTrue(result['ok'])
            self.assertFalse(result['result']['approval_granted'])
            artifact = core.verify_artifact(result['result']['poster_artifact_id'])
            self.assertEqual(artifact['role'], 'poster')
            self.assertIn(preview['id'], artifact['inputs'])
            status, _ = self.request(ctx, '/api/status')
            self.assertEqual(status['candidate_id'], candidate['id'])
            self.assertEqual(status['run_id'], candidate_run['id'])
            self.assertEqual(status['production_job']['run_id'], run['id'])
            self.assertEqual(status['production_job']['result']['poster_artifact_id'], artifact['id'])


    def test_studio_failed_poster_can_retry_without_losing_failure_evidence(self):
        from artifact_lifecycle import Lifecycle
        core = Lifecycle(self.root, self.config, self.cfg)
        run = core.start_run({})
        attempt = core.start_attempt(run['id'], 'preview', 'fixture-agent')
        video = self.root / 'preview.mp4'; video.write_bytes(b'fixture video')
        preview = core.register(attempt['id'], video, 'preview')
        core.finish_attempt(attempt['id'], 'succeeded')
        payload = {'run_id':run['id'], 'preview_id':preview['id'], 'timestamp':4}
        def failure(source, output, timestamp):
            output.write_bytes(b'partial frame'); raise ValueError('Frame decode failed')
        def success(source, output, timestamp):
            create_mock_png(output, 1920, 1080)
            return {'width':1920, 'height':1080, 'duration':15}
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = self.request(ctx, '/api/config')
            revision = {'If-Match': headers['ETag']}
            with mock.patch('managed_poster.extract', side_effect=failure):
                with self.assertRaises(urllib.error.HTTPError) as failed:
                    self.request(ctx, '/api/preview/poster', payload, revision)
                self.assertEqual(failed.exception.code, 400)
            status, _ = self.request(ctx, '/api/status')
            self.assertFalse(status['running'])
            self.assertEqual(status['error'], 'Frame decode failed')
            failed_attempt = next(item for item in core.status(run['id'])['attempts'] if item['stage'] == 'poster')
            payload['retry_of'] = failed_attempt['id']
            with mock.patch('managed_poster.extract', side_effect=success):
                result, _ = self.request(ctx, '/api/preview/poster', payload, revision)
            self.assertTrue(result['ok'])
            status, _ = self.request(ctx, '/api/status')
            self.assertFalse(status['running'])
            self.assertNotIn('error', status)
        attempts = [item for item in core.status(run['id'])['attempts'] if item['stage'] == 'poster']
        self.assertEqual(sorted(item['outcome']['status'] for item in attempts), ['failed', 'succeeded'])
        artifacts = [core._read('artifacts', path.stem)
            for path in (core.paths.workspace / 'records/artifacts').glob('*.json')]
        partial = next(item for item in artifacts if item['role'] == 'poster' and item['partial'])
        self.assertEqual(core.object_path(partial['sha256']).read_bytes(), b'partial frame')
        self.assertNotEqual(partial['attempt_id'], result['result']['attempt_id'])
        retried = next(item for item in attempts if item['outcome']['status'] == 'succeeded')
        self.assertEqual(retried['retry_of'], partial['attempt_id'])


    def test_run_query_survives_server_restart_and_reports_partial_artifacts(self):
        from artifact_lifecycle import Lifecycle
        core = Lifecycle(self.root, self.config, self.cfg)
        run = core.start_run({})
        attempt = core.start_attempt(run['id'], 'poster', 'fixture-agent')
        partial_path = self.root / 'partial.png'; partial_path.write_bytes(b'partial PNG')
        artifact = core.register(attempt['id'], partial_path, 'poster', partial=True,
                                 logical_path='preview/poster.png')
        core.finish_attempt(attempt['id'], 'failed', 'Frame decode failed')
        records = {str(path):path.read_bytes() for path in (core.paths.workspace / 'records').rglob('*.json')}
        for _ in range(2):
            with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
                result, _ = self.request(ctx, '/api/runs/' + run['id'])
                import subprocess
                cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
                command = subprocess.run([sys.executable, str(cli), 'run', 'status', '--repo',
                    str(self.root), '--id', run['id']], check=True, capture_output=True, text=True)
                self.assertEqual(result, json.loads(command.stdout))
                listing, _ = self.request(ctx, '/api/runs?limit=1')
                command = subprocess.run([sys.executable, str(cli), 'run', 'list', '--repo',
                    str(self.root), '--limit', '1'], check=True, capture_output=True, text=True)
                self.assertEqual(listing, json.loads(command.stdout))
                self.assertEqual(listing['runs'][0]['id'], run['id'])

                self.assertEqual(result['run']['id'], run['id'])
                self.assertEqual(result['attempts'][0]['outcome']['status'], 'failed')
                self.assertNotIn('token', result['attempts'][0]['lease'])
                item = next(item for item in result['artifacts'] if item['id'] == artifact['id'])
                self.assertTrue(item['partial'])
                self.assertEqual(item['object_integrity'], 'PASS')
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    self.request(ctx, '/api/runs/' + 'a'*32)
                self.assertEqual(missing.exception.code, 404)
        self.assertEqual(records, {str(path):path.read_bytes() for path in (core.paths.workspace / 'records').rglob('*.json')})

if __name__ == "__main__":
    unittest.main()
