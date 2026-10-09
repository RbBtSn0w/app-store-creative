"""Normalize native cadence without overwriting or extending acquisition evidence."""
import json
from pathlib import Path
import subprocess
from recording_adapters import validate_native_recording_probe, validate_recording_probe
from media_tool_identity import MediaTools


def normalize(plan, native, output, tools):
    native, output = Path(native), Path(output)
    if (not native.is_file() or native.is_symlink() or output.exists() or output.is_symlink()
            or native.resolve() == output.resolve()):
        raise ValueError('Normalization requires an original native take and a new output')
    tools.verify()
    native_sha = MediaTools.digest(native)
    def probe(path):
        result = subprocess.run([tools.paths['ffprobe'], '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(path)], check=True, capture_output=True,
            text=True, timeout=30)
        return json.loads(result.stdout)
    native_probe = probe(native)
    validate_native_recording_probe(plan, native_probe)
    command = [tools.paths['ffmpeg'], '-v', 'error', '-n', '-i', str(native),
        '-map', '0:v:0', '-an', '-vf', 'fps=' + str(plan['fps']), '-t', str(plan['duration']),
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-fps_mode', 'cfr', str(output)]
    subprocess.run(command, check=True, capture_output=True, timeout=plan['duration'] + 120)
    result_probe = probe(output)
    validate_recording_probe(plan, result_probe)
    tools.verify()
    if MediaTools.digest(native) != native_sha:
        raise ValueError('Native recording changed during normalization')
    return {'native_sha256': native_sha, 'native_probe': native_probe,
            'output_sha256': MediaTools.digest(output), 'probe': result_probe,
            'command': command, 'tools': tools.evidence}
