#!/usr/bin/env python3
"""Run opt-in relocation tests on an owned APFS image; persist cleanup evidence.

Use `run --state PATH --report PATH`, followed by `cleanup` with the same paths
in an always-running CI step. Never detaches volumes by name or with force.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def hdiutil(args):
    return subprocess.check_output(args, timeout=60)


def image_identity(image):
    stat = Path(image).stat()
    return [stat.st_dev, stat.st_ino]


def attached_image(state):
    info = plistlib.loads(hdiutil(['/usr/bin/hdiutil', 'info', '-plist']))
    images = [entry for entry in info.get('images', [])
              if Path(entry.get('image-path', '')).resolve() == Path(state['image']).resolve()]
    if len(images) > 1:
        raise RuntimeError('Ambiguous image identity')
    return images[0] if images else None


def cleanup(state, state_path=None):
    owned = Path(state['owned_dir'])
    image = Path(state['image'])
    mount = Path(state['mountpoint'])
    if (not owned.name.startswith('creative-crossfs-') or image.parent != owned
            or image.name != 'volume.sparseimage' or mount != owned / 'mount'
            or owned.is_symlink() or image.is_symlink() or mount.is_symlink()):
        raise RuntimeError('Unsafe owned workspace identity')
    if owned.exists() and state.get('owned_identity') != image_identity(owned):
        raise RuntimeError('Owned workspace identity changed; refusing cleanup')
    if image.exists() and state.get('image_identity') != image_identity(image):
        raise RuntimeError('Image file identity changed; refusing cleanup')
    persistence_error = None
    attached = attached_image(state)
    if attached:
        if not image.exists() or not state.get('image_identity'):
            raise RuntimeError('Cannot verify attached image identity')
        entities = attached.get('system-entities', [])
        devices = [entity.get('dev-entry') for entity in entities]
        device = state.get('device')
        if device:
            if device not in devices:
                raise RuntimeError('Device identity does not match owned image')
        else:
            # Attach can succeed before its response reaches the caller. Recover
            # only the exact image's whole device, never a global volume label.
            device = next((item for item in devices if item and item.startswith('/dev/disk')
                           and 's' not in item.removeprefix('/dev/disk')), None)
            if not device:
                raise RuntimeError('Cannot recover owned image device identity')
            state['device'] = device
        for entity in entities:
            point = entity.get('mount-point')
            if point and Path(point).resolve(strict=True) != mount.resolve(strict=True):
                raise RuntimeError('Owned image mounted at unexpected path')
        if state_path is not None:
            try:
                write_json(state_path, state)
            except OSError as error:
                persistence_error = error
        hdiutil(['/usr/bin/hdiutil', 'detach', device])
        if attached_image(state):
            raise RuntimeError('Owned image still attached after detach')
    if os.path.ismount(mount):
        raise RuntimeError('Mountpoint still active; refusing workspace removal')
    if owned.exists():
        shutil.rmtree(owned)
    state['attached'] = False
    if persistence_error is not None:
        raise persistence_error


def run_tests(repo, mount, report):
    command = [sys.executable, str(repo / '.github/run_sharded_tests.py'),
               '--shard', '1', '--total', '1', '--pattern', 'test_cross_filesystem*.py',
               '--fail-on-skip', '--report', str(report)]
    env = {**os.environ, 'CREATIVE_TEST_CROSSFS_ROOT': str(mount)}
    process = subprocess.Popen(command, cwd=repo, env=env, start_new_session=True)
    try:
        return process.wait(timeout=600)
    finally:
        # A watchdog can exit the leader while its workers still own volume files.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)



def run(repo: Path, state_path: Path, report_path: Path, temp_root: Path | None = None):
    if state_path.exists():
        raise RuntimeError('State already exists; run cleanup before starting a new run')
    owned = Path(tempfile.mkdtemp(prefix='creative-crossfs-', dir=temp_root)).resolve(strict=True)
    state = {'owned_dir': str(owned), 'image': str(owned / 'volume.sparseimage'),
             'mountpoint': str(owned / 'mount'), 'attached': False,
             'owned_identity': image_identity(owned)}
    source_sha = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    evidence = {'context': {'source_sha': source_sha, 'run_id': os.environ.get('GITHUB_RUN_ID')},
                'schema_version': 1, 'status': 'failed', 'volume': {'verified': False},
                'tests': None, 'cleanup': {'status': 'pending'}}
    write_json(state_path, state)
    write_json(report_path, evidence)
    try:
        mount, image = Path(state['mountpoint']), Path(state['image'])
        mount.mkdir()
        hdiutil(['/usr/bin/hdiutil', 'create', '-size', '1g', '-fs', 'APFS',
                 '-type', 'SPARSE', '-volname', owned.name, str(image)])
        state['image_identity'] = image_identity(image)
        write_json(state_path, state)
        attached = plistlib.loads(hdiutil(['/usr/bin/hdiutil', 'attach', '-plist',
                                         '-nobrowse', '-mountpoint', str(mount), str(image)]))
        entities = attached.get('system-entities', [])
        device = next((entry['dev-entry'] for entry in entities if entry.get('dev-entry')
                       and 's' not in entry['dev-entry'].removeprefix('/dev/disk')), None)
        if not device:
            raise RuntimeError('Attach did not identify the whole image device')
        state.update(device=device, attached=True)
        write_json(state_path, state)
        current = attached_image(state)
        if not current or not any(entry.get('dev-entry') == device
                                  for entry in current.get('system-entities', [])):
            raise RuntimeError('Attach device identity does not match owned image')
        if not any(entry.get('mount-point') and
                   Path(entry['mount-point']).resolve(strict=True) == mount.resolve(strict=True)
                   for entry in entities):
            raise RuntimeError('Attach did not confirm the owned mountpoint')
        source_device, target_device = tempfile.gettempdir(), mount.stat().st_dev
        source_device = Path(source_device).stat().st_dev
        if source_device == target_device or repo.stat().st_dev == target_device:
            raise RuntimeError('Mounted volume shares the source filesystem')
        evidence['volume'] = {'verified': True, 'source_device': source_device,
                              'target_device': target_device, 'image': str(image),
                              'mountpoint': str(mount), 'device': device}
        write_json(report_path, evidence)
        tests_report = owned / 'tests.json'
        returncode = run_tests(repo, mount, tests_report)
        evidence['tests'] = json.loads(tests_report.read_text())
        tests = evidence['tests']
        if (returncode or tests['tests_run'] <= 0 or tests['skipped'] or tests['problems']):
            raise RuntimeError('Strict cross-filesystem tests failed')
        evidence['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        evidence['error'] = f'{type(error).__name__}: {error}'
    finally:
        try:
            # Failed create may leave an image before returning an error.
            if Path(state['image']).exists() and not state.get('image_identity'):
                state['image_identity'] = image_identity(state['image'])
            cleanup(state, state_path)
            evidence['cleanup'] = {'status': 'passed'}
        except (Exception, KeyboardInterrupt) as error:
            evidence['status'] = 'failed'
            evidence['cleanup'] = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
        persist_result(state_path, state, report_path, evidence)
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'passed' else 1


def persist_result(state_path, state, report_path, evidence):
    try:
        write_json(state_path, state)
    except OSError as error:
        evidence['status'] = 'failed'
        evidence['state_error'] = f'{type(error).__name__}: {error}'
    write_json(report_path, evidence)
    return 'state_error' not in evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'cleanup'))
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise InterruptedError(f'Received signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    if args.command == 'run':
        return run(args.repo.resolve(), args.state.resolve(), args.report.resolve(),
                   Path(os.environ['RUNNER_TEMP']) if os.environ.get('RUNNER_TEMP') else None)
    if not args.state.exists():
        print('No owned volume state; nothing to clean up.')
        return 0
    state = json.loads(args.state.read_text())
    report_error = False
    try:
        evidence = json.loads(args.report.read_text())
        if not isinstance(evidence, dict):
            raise ValueError('Report must be an object')
    except (OSError, ValueError) as error:
        report_error = True
        evidence = {'schema_version': 1, 'status': 'failed', 'volume': {}, 'tests': None,
                    'error': f'Original report unavailable: {type(error).__name__}: {error}'}
    try:
        cleanup(state, args.state)
        evidence['cleanup'] = {'status': 'passed'}
        returncode = 1 if report_error else 0
    except Exception as error:
        evidence['status'] = 'failed'
        evidence['cleanup'] = {'status': 'failed', 'error': f'{type(error).__name__}: {error}'}
        returncode = 1
    if not persist_result(args.state, state, args.report, evidence):
        returncode = 1
    return returncode


if __name__ == '__main__':
    sys.exit(main())
