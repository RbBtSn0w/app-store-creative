#!/usr/bin/env python3
"""Plan or execute bounded ScreenCaptureKit recording without launching an app."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from recording_adapters import macos_recording_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-id', required=True)
    parser.add_argument('--list-windows', action='store_true')
    parser.add_argument('--window-id', type=int)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.list_windows:
            plan = {'operation': 'list-windows', 'bundle_id': args.bundle_id}
        else:
            if args.output is None or args.window_id is None:
                raise ValueError('--output and --window-id are required for recording')
            plan = macos_recording_plan(bundle_id=args.bundle_id, window_id=args.window_id,
                                        output=args.output.resolve(), duration=args.duration,
                                        width=args.width, height=args.height, fps=args.fps)
        if not args.execute:
            print(json.dumps({'executed': False, 'plan': plan})); return 0
        if platform.system() != 'Darwin' or int(platform.mac_ver()[0].split('.')[0]) < 15:
            raise ValueError('native recording requires macOS 15 or newer')
        if not shutil.which('xcrun'):
            raise ValueError('Xcode Command Line Tools with Swift are required')
        receipt = None
        if not args.list_windows:
            if not shutil.which('ffprobe'): raise ValueError('ffprobe is required to verify the recording')
            receipt = args.receipt or args.output.with_suffix('.receipt.json')
            if receipt.resolve() == args.output.resolve(): raise ValueError('receipt and output must be distinct')
            for path in (args.output, receipt):
                if path.exists(): raise ValueError(f'refusing to overwrite existing artifact: {path}')
                path.parent.mkdir(parents=True, exist_ok=True)
        helper_source = Path(__file__).with_suffix('.swift')
        with tempfile.TemporaryDirectory(prefix='creative-record-') as scratch:
            binary = Path(scratch) / 'record-app-window'
            compile_command = ['xcrun', 'swiftc', str(helper_source), '-o', str(binary)]
            subprocess.run(compile_command, check=True, capture_output=True)
            if args.list_windows:
                subprocess.run([str(binary), '--list', args.bundle_id], check=True)
                return 0
            contract_path = Path(scratch) / 'plan.json'
            contract_path.write_text(json.dumps(plan))
            command = [str(binary), '--record', str(contract_path)]
            # Stream recording-start signal so a caller can begin its app-specific journey.
            subprocess.run(command, check=True, timeout=args.duration + 60)
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(args.output)],
                                   check=True, capture_output=True, text=True)
            media = json.loads(probe.stdout)
            if float(media.get('format', {}).get('duration', 0)) <= 0 or not any(
                    s.get('codec_type') == 'video' and s.get('codec_name') == 'h264' for s in media.get('streams', [])):
                raise ValueError('recording is empty or has no H.264 video')
            with args.output.open('rb') as source:
                digest = hashlib.sha256()
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(block)
                sha = digest.hexdigest()
            result = {'schema_version': 1, 'producer': 'app-store-creative', 'kind': 'window-recording',
                      'plan': plan, 'command': command, 'compile_command': compile_command,
                      'recorder_source_sha256': hashlib.sha256(helper_source.read_bytes()).hexdigest(),
                      'output': {'path': str(args.output.resolve()), 'sha256': sha, 'probe': media}, 'uploaded': False}
            receipt.write_text(json.dumps(result, indent=2) + '\n')
            print(json.dumps({'executed': True, 'receipt': str(receipt.resolve())})); return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr, file=sys.stderr)
        print('No success receipt was written. Preserve any partial recording for diagnosis and retry with a new output path.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
