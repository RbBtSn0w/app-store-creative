"""Behavioral contract for managed creative attempts and content storage."""
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import artifact_lifecycle as lifecycle


class ArtifactLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.cfg = {'project': {'id': 'demo'}, 'storage': {
            'workspaceRoot': 'working area', 'objectRoot': 'objects',
            'releaseRoot': 'deliveries', 'publicationRoot': 'publications'}}
        self.store = lifecycle.Lifecycle(self.root, self.cfg)

    def test_custom_paths_are_project_relative(self):
        self.assertEqual(self.store.paths.workspace, self.root / 'working area')
        self.assertEqual(self.store.paths.objects, self.root / 'objects')
        self.assertFalse(self.store.paths.workspace.exists())

    def test_overlap_and_symlink_alias_fail_before_writes(self):
        for release in ('working area/release', '.', 'objects/release'):
            cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'releaseRoot': release}}
            with self.assertRaisesRegex(ValueError, 'overlap|project root'):
                lifecycle.Lifecycle(self.root, cfg)
        (self.root / 'alias').symlink_to(self.root / 'objects')
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'releaseRoot': 'alias'}}
        with self.assertRaisesRegex(ValueError, 'overlap'):
            lifecycle.Lifecycle(self.root, cfg)
        self.assertFalse((self.root / 'working area').exists())

    def test_attempts_preserve_outcomes_and_deduplicate_bytes(self):
        run = self.store.start_run({'version': '1.5'})
        first = self.store.start_attempt(run['id'], 'capture', 'agent-a')
        second = self.store.start_attempt(run['id'], 'capture', 'agent-b', retry_of=first['id'])
        source = self.root / 'sample.bin'; source.write_bytes(b'real product bytes')
        a = self.store.register(first['id'], source, 'capture', media_type='application/octet-stream')
        b = self.store.register(second['id'], source, 'capture', media_type='application/octet-stream')
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertEqual(len(list(self.store.paths.objects.glob('*/*'))), 1)
        self.store.finish_attempt(first['id'], 'failed', reason='Wrong locale')
        with self.assertRaisesRegex(ValueError, 'ended'):
            self.store.finish_attempt(first['id'], 'succeeded')
        with self.assertRaisesRegex(ValueError, 'ended'):
            self.store.register(first['id'], source, 'capture')
        self.assertEqual(self.store.status(run['id'])['attempts'][0]['outcome']['reason'], 'Wrong locale')

    def test_partial_artifacts_cannot_be_selected(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'agent')
        source = self.root / 'partial.bin'; source.write_bytes(b'partial')
        artifact = self.store.register(attempt['id'], source, 'capture', partial=True)
        self.store.finish_attempt(attempt['id'], 'failed', reason='Interrupted capture')
        with self.assertRaisesRegex(ValueError, 'partial|succeeded'):
            self.store.select(run['id'], [artifact['id']])

    def test_selection_requires_success_and_detects_object_corruption(self):
        run = self.store.start_run({}); attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source = self.root / 'render.bin'; source.write_bytes(b'approved bytes')
        artifact = self.store.register(attempt['id'], source, 'screenshot')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        candidate = self.store.select(run['id'], [artifact['id']])
        self.assertEqual(candidate['artifacts'], [artifact['id']])
        self.store.object_path(artifact['sha256']).write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.store.select(run['id'], [artifact['id']])

    def test_run_binds_storage_and_config_snapshot(self):
        run = self.store.start_run({})
        changed = {**self.cfg, 'storage': {**self.cfg['storage'], 'objectRoot': 'new-objects'}}
        moved = lifecycle.Lifecycle(self.root, changed)
        with self.assertRaisesRegex(ValueError, 'storage'):
            moved.start_attempt(run['id'], 'render', 'agent')
        self.cfg['project']['id'] = 'edited-after-start'
        self.assertEqual(self.store.status(run['id'])['run']['config']['project']['id'], 'demo')

    def test_cli_uses_the_same_directory_and_record_contract(self):
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        (self.root / 'creative.config.json').write_text(json.dumps(self.cfg))
        (self.root / 'target.json').write_text(json.dumps({'version': '1.5'}))
        process = subprocess.run([sys.executable, str(cli), 'run', '--repo', str(self.root),
                                  'start', '--target', 'target.json'], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        run = json.loads(process.stdout)
        self.assertEqual(self.store.status(run['id'])['run']['target']['version'], '1.5')

    def test_git_policy_uses_custom_roots_without_mutating_user_rules(self):
        (self.root / '.gitignore').write_text('user-cache/\n')
        result = self.store.git_policy('lfs')
        self.assertIn('/working area/', result['gitignore'])
        self.assertIn('/objects/', result['gitignore'])
        self.assertIn('deliveries/**/media/** filter=lfs diff=lfs merge=lfs -text', result['gitattributes'])
        self.assertEqual((self.root / '.gitignore').read_text(), 'user-cache/\n')
        self.assertFalse((self.root / '.gitattributes').exists())

    def test_object_storage_cannot_be_shared_without_reference_protection(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'agent')
        source = self.root / 'source.bin'; source.write_bytes(b'object')
        self.store.register(attempt['id'], source, 'capture')
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'workspaceRoot': 'other-working'}}
        other = lifecycle.Lifecycle(self.root, cfg)
        second_run = other.start_run({})
        second_attempt = other.start_attempt(second_run['id'], 'capture', 'agent')
        with self.assertRaisesRegex(ValueError, 'owned|shared'):
            other.register(second_attempt['id'], source, 'capture')

    def test_cli_accepts_project_options_after_nested_command(self):
        import app_store_creative
        args = app_store_creative.build_parser().parse_args(['run', 'start', '--repo', str(self.root), '--target', 'target.json'])
        self.assertEqual(args.repo, self.root)

    def test_workspace_owner_cannot_change(self):
        self.store.start_run({})
        other = {**self.cfg, 'project': {'id': 'another'}}
        with self.assertRaisesRegex(ValueError, 'owned'):
            lifecycle.Lifecycle(self.root, other).start_run({})

    def test_object_root_cannot_equal_workspace(self):
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'objectRoot': 'working area'}}
        with self.assertRaisesRegex(ValueError, 'overlap'):
            lifecycle.Lifecycle(self.root, cfg)

    def test_paths_outside_project_must_be_explicit_absolute(self):
        cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'objectRoot': '../outside'}}
        with self.assertRaisesRegex(ValueError, 'relative'):
            lifecycle.Lifecycle(self.root, cfg)

    def test_unregistered_work_files_are_reported_not_deleted(self):
        run = self.store.start_run({}); attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        unknown = self.store.work_path(attempt['id']) / 'forgotten.png'; unknown.write_bytes(b'unknown')
        result = self.store.inventory()
        self.assertIn(str(unknown), result['unregistered_files'])
        self.assertTrue(unknown.exists())


    def test_run_status_reports_corrupt_artifact_without_erasing_history(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'capture', 'agent')
        path = self.root / 'capture.png'; path.write_bytes(b'fixture capture')
        artifact = self.store.register(attempt['id'], path, 'capture')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        status = self.store.status(run['id'])
        self.assertEqual(status['artifacts'][0]['object_integrity'], 'PASS')
        self.store.object_path(artifact['sha256']).write_bytes(b'corrupt')
        status = self.store.status(run['id'])
        self.assertEqual(status['artifacts'][0]['object_integrity'], 'FAIL')
        self.assertEqual(status['artifacts'][0]['sha256'], artifact['sha256'])
        self.assertEqual(status['attempts'][0]['outcome']['status'], 'succeeded')


    def test_intact_partial_and_unfinished_artifacts_are_not_candidate_eligible(self):
        for state in ('partial', 'unfinished', 'failed', 'succeeded'):
            with self.subTest(state=state):
                run = self.store.start_run({})
                attempt = self.store.start_attempt(run['id'], 'capture', 'agent')
                path = self.root / 'capture.png'; path.write_bytes(b'capture fixture')
                self.store.register(attempt['id'], path, 'capture', partial=state == 'partial')
                if state != 'unfinished':
                    self.store.finish_attempt(attempt['id'], 'failed' if state == 'failed' else 'succeeded',
                                              'Fixture failure' if state == 'failed' else None)
                artifact = self.store.status(run['id'])['artifacts'][0]
                self.assertEqual(artifact['object_integrity'], 'PASS')
                self.assertEqual(artifact['candidate_eligible'], state == 'succeeded')
                self.assertEqual(bool(artifact['eligibility_errors']), state != 'succeeded')


    def test_failed_or_corrupt_source_prevents_output_selection(self):
        for state in ('failed', 'corrupt'):
            with self.subTest(state=state):
                run = self.store.start_run({})
                capture_attempt = self.store.start_attempt(run['id'], 'capture', 'agent')
                path = self.root / 'source.png'; path.write_bytes(b'capture fixture')
                source = self.store.register(capture_attempt['id'], path, 'capture')
                self.store.finish_attempt(capture_attempt['id'], 'failed' if state == 'failed' else 'succeeded',
                                          'Capture failed' if state == 'failed' else None)
                render_attempt = self.store.start_attempt(run['id'], 'render', 'agent')
                output_path = self.root / 'output.png'; output_path.write_bytes(b'rendered fixture')
                output = self.store.register(render_attempt['id'], output_path, 'screenshot', inputs=[source['id']])
                self.store.finish_attempt(render_attempt['id'], 'succeeded')
                if state == 'corrupt':
                    self.store.object_path(source['sha256']).write_bytes(b'corrupt source')
                status = self.store.status(run['id'])
                displayed = next(item for item in status['artifacts'] if item['id'] == output['id'])
                self.assertEqual(displayed['object_integrity'], 'PASS')
                self.assertFalse(displayed['candidate_eligible'])
                with self.assertRaisesRegex(ValueError, 'source|Source'):
                    self.store.select(run['id'], [output['id']])


    def test_run_status_rechecks_candidate_sources_without_rewriting_selection(self):
        run = self.store.start_run({})
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        source_path = self.root / 'source'; source_path.write_bytes(b'source fixture')
        source = self.store.register(attempt['id'], source_path, 'source')
        output_path = self.root / 'output'; output_path.write_bytes(b'output fixture')
        output = self.store.register(attempt['id'], output_path, 'screenshot', inputs=[source['id']])
        self.store.finish_attempt(attempt['id'], 'succeeded')
        candidate = self.store.select(run['id'], [output['id']])
        original = self.store._path('candidates', candidate['id']).read_bytes()
        status = self.store.status(run['id'])
        self.assertEqual(status['candidates'][0]['source_status'], 'PASS')
        self.store.object_path(source['sha256']).write_bytes(b'corrupt')
        status = self.store.status(run['id'])
        self.assertEqual(status['candidates'][0]['source_status'], 'FAIL')
        self.assertTrue(status['candidates'][0]['source_errors'])
        self.assertEqual(self.store._path('candidates', candidate['id']).read_bytes(), original)


    def test_run_list_pagination_is_stable_when_new_runs_arrive(self):
        runs = [self.store.start_run({'version':str(index)}) for index in range(3)]
        first = self.store.list_runs(limit=2)
        self.assertEqual([item['id'] for item in first['runs']], [runs[2]['id'], runs[1]['id']])
        self.store.start_run({'version':'new'})
        second = self.store.list_runs(limit=2, cursor=first['next_cursor'])
        self.assertEqual([item['id'] for item in second['runs']], [runs[0]['id']])
        self.assertIsNone(second['next_cursor'])
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                self.store.list_runs(limit=limit)
        with self.assertRaises(ValueError):
            self.store.list_runs(cursor='missing')

    def test_lfs_policy_matches_literal_custom_release_directory(self):
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        for name in ('媒体 assets', 'archive [set]', 'archive *', 'archive "one"'):
            with self.subTest(name=name):
                cfg = {**self.cfg, 'storage': {**self.cfg['storage'], 'releaseRoot': name}}
                core = lifecycle.Lifecycle(self.root, cfg)
                policy = core.git_policy('lfs')
                (self.root/'.gitattributes').write_text('\n'.join(policy['gitattributes'])+'\n')
                media = name+'/revision/media/shot.png'
                response = subprocess.run(['git', '-C', str(self.root), 'check-attr', '-z',
                    'filter', '--', media], check=True, capture_output=True)
                self.assertEqual(response.stdout.split(b'\0')[2], b'lfs')
                other = name.replace('[set]', 's').replace('*', 'other')
                if other != name:
                    response = subprocess.run(['git', '-C', str(self.root), 'check-attr', '-z',
                        'filter', '--', other+'/revision/media/shot.png'], check=True, capture_output=True)
                    self.assertEqual(response.stdout.split(b'\0')[2], b'unspecified')

if __name__ == '__main__':
    unittest.main()
