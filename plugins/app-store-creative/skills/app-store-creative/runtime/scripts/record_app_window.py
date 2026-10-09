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

from recording_adapters import macos_recording_plan, validate_recording_probe


def compile_recorder(source, binary):
    """Compile a pinned source and retain portable compiler/binary identities."""
    import re
    from media_tool_identity import MediaTools
    xcrun = shutil.which('xcrun')
    if xcrun is None:
        raise ValueError('Xcode Command Line Tools with Swift are required')
    resolved = subprocess.run([xcrun, '--find', 'swiftc'], check=True, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    compiler = Path(resolved)
    if not compiler.is_absolute() or not compiler.is_file():
        raise ValueError('Swift compiler locator returned an invalid executable')
    compiler_sha = MediaTools.digest(compiler)
    version = subprocess.run([str(compiler), '--version'], check=True, capture_output=True,
                             text=True, timeout=10).stdout
    match = re.match(r'(?:Apple )?Swift version ([A-Za-z0-9_.+-]{1,80})', version)
    if not match:
        raise ValueError('Swift compiler version evidence is invalid')
    source_sha = MediaTools.digest(source)
    sdk = subprocess.run([xcrun, '--sdk', 'macosx', '--show-sdk-path'], check=True,
                         capture_output=True, text=True, timeout=10).stdout.strip()
    sdk_version = subprocess.run([xcrun, '--sdk', 'macosx', '--show-sdk-version'], check=True,
                                 capture_output=True, text=True, timeout=10).stdout.strip()
    architecture = platform.machine()
    if architecture not in ('arm64', 'x86_64') or not Path(sdk).is_absolute() or not Path(sdk).is_dir():
        raise ValueError('Recorder requires a supported architecture and macOS SDK')
    if not re.fullmatch(r'[0-9.]{1,32}', sdk_version):
        raise ValueError('Recorder SDK version evidence is invalid')
    target = architecture + '-apple-macosx15.0'
    command = [str(compiler), '-sdk', sdk, '-target', target, str(source), '-o', str(binary)]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    if MediaTools.digest(source) != source_sha or MediaTools.digest(compiler) != compiler_sha:
        raise ValueError('Recorder source or compiler changed during compilation')
    return command, {'name': 'swiftc', 'version': match[1], 'executable_sha256': compiler_sha,
                     'sdk_version': sdk_version, 'target': target}, source_sha


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
            if not shutil.which('ffprobe') or not shutil.which('ffmpeg'):
                raise ValueError('ffmpeg and ffprobe are required to normalize the recording')
            receipt = args.receipt or args.output.with_suffix('.receipt.json')
            if receipt.resolve() == args.output.resolve(): raise ValueError('receipt and output must be distinct')
            native_output = args.output.with_name(args.output.stem + ".native.mov")
            for path in (args.output, native_output, receipt):
                if path.exists(): raise ValueError(f'refusing to overwrite existing artifact: {path}')
                path.parent.mkdir(parents=True, exist_ok=True)
        helper_source = Path(__file__).with_suffix('.swift')
        with tempfile.TemporaryDirectory(prefix='creative-record-') as scratch:
            binary = Path(scratch) / 'record-app-window'
            compile_command, compiler_identity, source_sha = compile_recorder(helper_source, binary)
            from media_tool_identity import MediaTools
            binary_sha = MediaTools.digest(binary)
            if args.list_windows:
                subprocess.run([str(binary), '--list', args.bundle_id], check=True)
                return 0
            contract_path = Path(scratch) / 'plan.json'
            contract_path.write_text(json.dumps({**plan, "output": str(native_output.resolve())}))
            tools = MediaTools()
            command = [str(binary), '--record', str(contract_path)]
            # Stream recording-start signal so a caller can begin its app-specific journey.
            subprocess.run(command, check=True, timeout=args.duration + 60)
            from recording_normalization import normalize
            normalization = normalize(plan, native_output, args.output, tools)
            media = normalization['probe']
            sha = normalization['output_sha256']
            if MediaTools.digest(binary) != binary_sha or MediaTools.digest(helper_source) != source_sha:
                raise ValueError('Recorder implementation changed during execution')
            result = {'schema_version': 1, 'producer': 'app-store-creative', 'kind': 'window-recording',
                      'plan': plan, 'command': command, 'compile_command': compile_command,
                      'recorder_source_sha256': source_sha,
                      'execution_identity': {'compiler': compiler_identity, 'recorder_executable_sha256': binary_sha,
                          'probe_tools': [item for item in tools.evidence if item['name'] == 'ffprobe'], 'environment': {'os': platform.system(),
                              'os_version': platform.mac_ver()[0], 'architecture': platform.machine()}},
                      'native_output': {'path': str(native_output.resolve()), 'sha256': normalization['native_sha256']},
                      'normalization': normalization,
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
