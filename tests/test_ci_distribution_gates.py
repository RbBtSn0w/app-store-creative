"""Regression protection for distribution freshness and mandatory CI evidence."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github'))


class StudioDistTests(unittest.TestCase):
    def test_compares_head_and_detects_ignored_untracked_staged_and_deleted(self):
        script = ROOT / '.github/check_studio_dist.py'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True)
            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'Test')
            dist = root / 'dist'
            dist.mkdir()
            asset = dist / 'asset.js'
            asset.write_text('original')
            (root / '.gitignore').write_text('*.ignored\n')
            git('add', '.')
            git('commit', '-qm', 'fixture')
            def check():
                return subprocess.run([sys.executable, str(script), '--repo', str(root),
                                       '--dist', 'dist'], capture_output=True, text=True)
            self.assertEqual(check().returncode, 0, check().stderr)
            for mutation in ('ignored', 'untracked', 'modified', 'staged', 'deleted'):
                with self.subTest(mutation=mutation):
                    asset.write_text('original')
                    if mutation in ('ignored', 'untracked'):
                        extra = dist / ('new.ignored' if mutation == 'ignored' else 'new.js')
                        extra.write_text('extra')
                    elif mutation == 'deleted':
                        asset.unlink()
                    else:
                        asset.write_text('changed')
                        if mutation == 'staged':
                            git('add', 'dist')
                    self.assertNotEqual(check().returncode, 0)
                    if mutation in ('ignored', 'untracked'):
                        extra.unlink()
                    if mutation == 'staged':
                        git('reset', '-q', 'HEAD', '--', 'dist')


class StrictRunnerTests(unittest.TestCase):
    def test_strict_skip_and_zero_fail_but_default_is_unchanged(self):
        runner = importlib.import_module('run_sharded_tests')
        for count, skips, strict, expected in ((1, [], False, 0), (1, [1], False, 0),
                                               (1, [1], True, 1), (0, [], True, 1)):
            with self.subTest(count=count, skips=skips, strict=strict):
                result = mock.Mock(testsRun=count, skipped=skips, failures=[], errors=[])
                result.wasSuccessful.return_value = True
                args = ['runner', '--test-timeout', '0'] + (['--fail-on-skip'] if strict else [])
                with mock.patch.object(sys, 'argv', args), \
                        mock.patch.object(runner.WatchdogResult, 'test_timeout', runner.WatchdogResult.test_timeout), \
                        mock.patch.object(runner, 'discover_and_shard', return_value=[]), \
                        mock.patch.object(runner.unittest.TextTestRunner, 'run', return_value=result):
                    self.assertEqual(runner.main(), expected)


class RequiredCrossfsSummaryTests(unittest.TestCase):
    def test_required_missing_malformed_failed_and_cleanup_failure_are_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'crossfs.json'
            shards = root / 'shards'
            shards.mkdir()
            (shards / 'shard-1.json').write_text(json.dumps({
                'shard': 1, 'tests_run': 1, 'started_at': 0, 'elapsed': 1,
                'problems': [], 'skipped': [], 'slowest': []}))
            base = {'context': {'source_sha': 'test-sha', 'run_id': 'test-run'},
                    'schema_version': 1, 'status': 'passed', 'cleanup': {'status': 'passed'},
                    'volume': {'source_device': 1, 'target_device': 2, 'verified': True},
                    'tests': {'tests_run': 1, 'problems': [], 'skipped': []}}
            for content, passing in ((None, False), ('{', False), ('[]', False),
                                     (json.dumps(base), True),
                                     (json.dumps({**base, 'context': {'source_sha': 'old', 'run_id': 'test-run'}}), False),
                                     (json.dumps({**base, 'context': {'source_sha': 'test-sha', 'run_id': 'old'}}), False),
                                     (json.dumps({**base, 'status': 'failed'}), False),
                                     (json.dumps({**base, 'cleanup': {'status': 'failed'}}), False)):
                with self.subTest(content=content):
                    if content is not None:
                        report.write_text(content)
                    proc = subprocess.run([sys.executable, str(ROOT / '.github/ci_test_report.py'),
                                           str(root / 'shards'), '--shards', '1',
                                           '--crossfs-report', str(report), '--require-crossfs'],
                                          capture_output=True, text=True,
                                          env={'GITHUB_SHA': 'test-sha', 'GITHUB_RUN_ID': 'test-run'})
                    self.assertEqual(proc.returncode, 0 if passing else 1, proc.stderr)
                    self.assertTrue(proc.stdout.startswith('## ✅' if passing else '## ❌'),
                                    proc.stdout + proc.stderr)


class CrossfsLifecycleTests(unittest.TestCase):
    def test_attach_failure_and_create_failure_still_write_failed_report_and_cleanup(self):
        harness = importlib.import_module('run_crossfs_tests')
        for failure in ('create', 'attach'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report, state = root / 'report.json', root / 'state.json'
                def command(args, **kwargs):
                    if args[1] == failure:
                        raise subprocess.CalledProcessError(1, args)
                    if args[1] == 'create':
                        Path(args[-1]).write_bytes(b'image')
                    if args[1] == 'info':
                        import plistlib
                        return plistlib.dumps({'images': []})
                    return b''
                with mock.patch.object(harness, 'hdiutil', side_effect=command), \
                        mock.patch('builtins.print'):
                    self.assertEqual(harness.run(ROOT, state, report, root), 1)
                evidence = json.loads(report.read_text())
                self.assertEqual(evidence['status'], 'failed')
                self.assertEqual(evidence['cleanup']['status'], 'passed')
                self.assertFalse(Path(json.loads(state.read_text())['owned_dir']).exists())

    def test_cleanup_refuses_device_identity_mismatch(self):
        harness = importlib.import_module('run_crossfs_tests')
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owned = root / 'creative-crossfs-owned'
            owned.mkdir()
            image = owned / 'volume.sparseimage'
            image.write_bytes(b'image')
            stat = image.stat()
            state = {'owned_dir': str(owned), 'owned_identity': harness.image_identity(owned),
                     'image': str(image),
                     'image_identity': [stat.st_dev, stat.st_ino],
                     'mountpoint': str(owned / 'mount'), 'device': '/dev/disk12',
                     'attached': True}
            info = plistlib.dumps({'images': [{'image-path': str(image),
                                  'system-entities': [{'dev-entry': '/dev/disk99'}]}]})
            with mock.patch.object(harness, 'hdiutil', return_value=info):
                with self.assertRaisesRegex(RuntimeError, 'identity'):
                    harness.cleanup(state)
            self.assertTrue(image.exists())

    def test_cleanup_detach_failure_preserves_image_for_retry(self):
        harness = importlib.import_module('run_crossfs_tests')
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            owned = Path(directory) / 'creative-crossfs-owned'
            owned.mkdir()
            image = owned / 'volume.sparseimage'
            image.write_bytes(b'image')
            stat = image.stat()
            state = {'owned_dir': str(owned), 'owned_identity': harness.image_identity(owned),
                     'image': str(image),
                     'image_identity': [stat.st_dev, stat.st_ino],
                     'mountpoint': str(owned / 'mount'), 'device': '/dev/disk12',
                     'attached': True}
            def command(args, **kwargs):
                if args[1] == 'info':
                    return plistlib.dumps({'images': [{'image-path': str(image),
                        'system-entities': [{'dev-entry': '/dev/disk12'}]}]})
                raise subprocess.CalledProcessError(1, args)
            with mock.patch.object(harness, 'hdiutil', side_effect=command):
                with self.assertRaises(subprocess.CalledProcessError):
                    harness.cleanup(state)
            self.assertTrue(image.exists())

    def test_lifecycle_records_realistic_external_failures_without_false_success(self):
        harness = importlib.import_module('run_crossfs_tests')
        import plistlib
        import types
        for outcome in ('passed', 'mount-alias', 'same-device', 'timeout', 'signal', 'skip',
                        'test-failure', 'detach-failure', 'partial-attach', 'bad-plist', 'wrong-mount'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report, state_file = root / 'report.json', root / 'state.json'
                active = False
                mountpoint = None
                original_stat = Path.stat
                def stat(path, *args, **kwargs):
                    actual = original_stat(path, *args, **kwargs)
                    if mountpoint and path == mountpoint and active:
                        return types.SimpleNamespace(st_dev=(actual.st_dev if outcome == 'same-device'
                                                            else actual.st_dev + 100))
                    return actual
                def entities():
                    return [{'dev-entry': '/dev/disk12'},
                            {'dev-entry': '/dev/disk12s1',
                             'mount-point': str(root / 'mount-alias' if outcome == 'mount-alias'
                                                else mountpoint if outcome != 'wrong-mount' else root)}]
                def command(args):
                    nonlocal active, mountpoint
                    action = args[1]
                    if action == 'create':
                        Path(args[-1]).write_bytes(b'image')
                        return b''
                    if action == 'attach':
                        active = True
                        mountpoint = Path(args[args.index('-mountpoint') + 1])
                        if outcome == 'mount-alias':
                            (root / 'mount-alias').symlink_to(mountpoint, target_is_directory=True)
                        if outcome == 'partial-attach':
                            raise subprocess.CalledProcessError(1, args)
                        if outcome == 'bad-plist':
                            return b'invalid'
                        return plistlib.dumps({'system-entities': entities()})
                    if action == 'info':
                        state = json.loads(state_file.read_text())
                        images = [{'image-path': state['image'], 'system-entities': entities()}] if active else []
                        return plistlib.dumps({'images': images})
                    if action == 'detach':
                        if outcome == 'detach-failure':
                            raise subprocess.CalledProcessError(1, args)
                        active = False
                        return b''
                    self.fail(f'Unexpected hdiutil action: {action}')
                def tests(repo, mount, path):
                    if outcome == 'timeout':
                        raise subprocess.TimeoutExpired('runner', 600)
                    if outcome == 'signal':
                        raise InterruptedError('Received signal 15')
                    path.write_text(json.dumps({'tests_run': 2, 'problems': [],
                                                'skipped': ['skip'] if outcome == 'skip' else []}))
                    return 1 if outcome == 'test-failure' else 0
                with mock.patch.object(harness, 'hdiutil', side_effect=command), \
                        mock.patch.object(Path, 'stat', stat), \
                        mock.patch.object(harness, 'run_tests', side_effect=tests), \
                        mock.patch('builtins.print'):
                    result = harness.run(ROOT, state_file, report, root)
                evidence = json.loads(report.read_text())
                self.assertEqual(result, 0 if outcome in ('passed', 'mount-alias') else 1)
                self.assertEqual(evidence['status'], 'passed' if outcome in ('passed', 'mount-alias') else 'failed')
                cleanup_failed = outcome in ('detach-failure', 'wrong-mount')
                self.assertEqual(evidence['cleanup']['status'], 'failed' if cleanup_failed else 'passed')
                self.assertEqual(active, cleanup_failed)
                self.assertEqual(Path(json.loads(state_file.read_text())['owned_dir']).exists(), cleanup_failed)

    def test_cleanup_refuses_replaced_owned_directory(self):
        harness = importlib.import_module('run_crossfs_tests')
        with tempfile.TemporaryDirectory() as directory:
            owned = Path(directory) / 'creative-crossfs-owned'
            owned.mkdir()
            image = owned / 'volume.sparseimage'
            image.write_bytes(b'image')
            original = owned.stat()
            state = {'owned_dir': str(owned), 'owned_identity': [original.st_dev, original.st_ino],
                     'image': str(image), 'image_identity': harness.image_identity(image),
                     'mountpoint': str(owned / 'mount')}
            owned.rename(owned.with_name('preserved'))
            owned.mkdir()
            (owned / 'sentinel').write_text('must remain')
            with mock.patch.object(harness, 'hdiutil', return_value=__import__('plistlib').dumps({'images': []})):
                with self.assertRaisesRegex(RuntimeError, 'workspace identity'):
                    harness.cleanup(state)
            self.assertTrue((owned / 'sentinel').exists())

    def test_cleanup_accepts_canonical_mountpoint_alias(self):
        harness = importlib.import_module('run_crossfs_tests')
        import plistlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / 'actual'
            actual.mkdir()
            alias = root / 'alias'
            alias.symlink_to(actual, target_is_directory=True)
            owned = actual / 'creative-crossfs-owned'
            owned.mkdir()
            (owned / 'mount').mkdir()
            image = owned / 'volume.sparseimage'
            image.write_bytes(b'image')
            state = {'owned_dir': str(owned), 'owned_identity': harness.image_identity(owned),
                     'image': str(image), 'image_identity': harness.image_identity(image),
                     'mountpoint': str(owned / 'mount'), 'device': '/dev/disk12'}
            attached = plistlib.dumps({'images': [{'image-path': str(image),
                'system-entities': [{'dev-entry': '/dev/disk12',
                    'mount-point': str(alias / owned.name / 'mount')}]}]})
            detached = plistlib.dumps({'images': []})
            with mock.patch.object(harness, 'hdiutil', side_effect=[attached, b'', detached]):
                harness.cleanup(state)
            self.assertFalse(owned.exists())
            self.assertTrue(alias.exists())


class UnexpectedSuccessEvidenceTests(unittest.TestCase):
    def test_runner_report_diagnoses_unexpected_success(self):
        import io
        runner = importlib.import_module('run_sharded_tests')
        result = runner.WatchdogResult(unittest.runner._WritelnDecorator(io.StringIO()), True, 0)
        case = unittest.FunctionTestCase(lambda: None, description='unexpected success')
        result.testsRun = 1
        result.unexpectedSuccesses.append(case)
        report = runner.build_report(1, 1, result, 0, 1, ROOT)
        self.assertEqual(report['problems'][0]['kind'], 'unexpected_success')
        self.assertIn('Unexpected success', report['problems'][0]['message'])
        self.assertFalse(report['successful'])

    def test_unsuccessful_regular_report_fails_render_and_required_summary(self):
        summary = importlib.import_module('ci_test_report')
        report = {'shard': 1, 'tests_run': 1, 'started_at': 0, 'elapsed': 1,
                  'problems': [], 'skipped': [], 'slowest': [], 'successful': False}
        markdown = summary.render([report], 1)
        self.assertTrue(markdown.startswith('## ❌'), markdown)
        self.assertIn('| 1/1 | ❌ Failed |', markdown)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shards = root / 'shards'
            shards.mkdir()
            (shards / 'shard.json').write_text(json.dumps(report))
            crossfs = root / 'crossfs.json'
            crossfs.write_text(json.dumps({
                'schema_version': 1, 'context': {'source_sha': 'test-sha', 'run_id': 'test-run'},
                'status': 'passed', 'cleanup': {'status': 'passed'},
                'volume': {'source_device': 1, 'target_device': 2, 'verified': True},
                'tests': {'tests_run': 1, 'problems': [], 'skipped': []}}))
            proc = subprocess.run([sys.executable, str(ROOT / '.github/ci_test_report.py'),
                                   str(shards), '--shards', '1', '--crossfs-report', str(crossfs),
                                   '--require-crossfs'], capture_output=True, text=True,
                                  env={'GITHUB_SHA': 'test-sha', 'GITHUB_RUN_ID': 'test-run'})
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertTrue(proc.stdout.startswith('## ❌'))


class CleanupEvidenceRecoveryTests(unittest.TestCase):
    def test_cleanup_runs_even_when_original_report_is_malformed_or_unreadable(self):
        harness = importlib.import_module('run_crossfs_tests')
        import plistlib
        for failure in ('malformed', 'unreadable'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                owned = root / 'creative-crossfs-owned'
                owned.mkdir()
                image = owned / 'volume.sparseimage'
                image.write_bytes(b'image')
                state = root / 'state.json'
                report = root / 'report.json'
                state.write_text(json.dumps({
                    'owned_dir': str(owned), 'owned_identity': harness.image_identity(owned),
                    'image': str(image), 'image_identity': harness.image_identity(image),
                    'mountpoint': str(owned / 'mount')}))
                report.write_text('{')
                original_read = Path.read_text
                def read(path, *args, **kwargs):
                    if failure == 'unreadable' and path == report:
                        raise PermissionError('report read denied')
                    return original_read(path, *args, **kwargs)
                with mock.patch.object(sys, 'argv', ['harness', 'cleanup', '--state', str(state),
                                                    '--report', str(report)]), \
                        mock.patch.object(Path, 'read_text', read), \
                        mock.patch.object(harness, 'hdiutil', return_value=plistlib.dumps({'images': []})), \
                        mock.patch.object(harness.signal, 'signal'):
                    self.assertEqual(harness.main(), 1)
                self.assertFalse(owned.exists())
                evidence = json.loads(report.read_text())
                self.assertEqual(evidence['status'], 'failed')
                self.assertEqual(evidence['cleanup']['status'], 'passed')
                self.assertIn('report', evidence['error'].lower())


class ReviewCleanupRegressionTests(unittest.TestCase):
    def test_exited_runner_still_reaps_descendants(self):
        import os
        import select
        import signal
        harness = importlib.import_module('run_crossfs_tests')
        original = subprocess.Popen
        processes = []
        program = ('import subprocess,sys; '
                   'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                   'print(p.pid,flush=True); sys.exit(1)')
        def launch(command, **kwargs):
            process = original([sys.executable, '-c', program], stdout=subprocess.PIPE, **kwargs)
            processes.append(process)
            process.stdout.readline()
            return process
        try:
            with mock.patch.object(harness.subprocess, 'Popen', launch):
                self.assertEqual(harness.run_tests(ROOT, Path('/tmp'), Path('/tmp/unused-review-report')), 1)
            ready, _, _ = select.select([processes[0].stdout], [], [], 1)
            self.assertTrue(ready, 'Descendant still holds the runner output pipe')
            self.assertEqual(processes[0].stdout.read(), b'')
        finally:
            for process in processes:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                process.stdout.close()

    def test_state_write_failure_does_not_prevent_verified_detach(self):
        harness = importlib.import_module('run_crossfs_tests')
        with tempfile.TemporaryDirectory() as directory:
            owned = Path(directory) / 'creative-crossfs-owned'; owned.mkdir()
            image = owned / 'volume.sparseimage'; image.write_bytes(b'fixture')
            mount = owned / 'mount'; mount.mkdir()
            state = {'owned_dir': str(owned), 'owned_identity': harness.image_identity(owned),
                     'image': str(image), 'image_identity': harness.image_identity(image),
                     'mountpoint': str(mount), 'device': '/dev/disk999'}
            attached = {'system-entities': [{'dev-entry': '/dev/disk999', 'mount-point': str(mount)}]}
            with mock.patch.object(harness, 'attached_image', side_effect=[attached, None]), \
                    mock.patch.object(harness, 'hdiutil') as command, \
                    mock.patch.object(harness, 'write_json', side_effect=OSError('state unavailable')):
                with self.assertRaisesRegex(OSError, 'state unavailable'):
                    harness.cleanup(state, Path(directory) / 'state.json')
            command.assert_called_once_with(['/usr/bin/hdiutil', 'detach', '/dev/disk999'])
            self.assertFalse(owned.exists())

    def test_state_failure_still_persists_failed_result(self):
        harness = importlib.import_module('run_crossfs_tests')
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / 'state.json'
            report_path = Path(directory) / 'report.json'
            evidence = {'status': 'passed'}
            original = harness.write_json
            def write(path, value):
                if path == state_path:
                    raise OSError('state unavailable')
                original(path, value)
            with mock.patch.object(harness, 'write_json', write):
                self.assertFalse(harness.persist_result(state_path, {}, report_path, evidence))
            self.assertEqual(json.loads(report_path.read_text())['status'], 'failed')
