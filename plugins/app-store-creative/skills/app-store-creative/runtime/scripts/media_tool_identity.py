"""Resolve media executables once and preserve portable binary/version evidence."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess


class MediaTools:
    def __init__(self, names=('ffmpeg', 'ffprobe')):
        self.paths = {}
        self.evidence = []
        if not names or any(name not in ('ffmpeg', 'ffprobe') for name in names):
            raise ValueError('Unsupported media tool identity request')
        for name in names:
            selected = shutil.which(name)
            if selected is None:
                raise ValueError('Required media tool unavailable: ' + name)
            path = Path(selected).resolve()
            if not path.is_file():
                raise ValueError('Media tool is not a regular executable: ' + name)
            before = self.digest(path)
            output = subprocess.run([str(path), '-version'], check=True, capture_output=True,
                                    text=True, timeout=10).stdout.splitlines()
            parts = output[0].split() if output else []
            if (len(parts) < 3 or parts[:2] != [name, 'version']
                    or not re.fullmatch(r'[A-Za-z0-9_.+~:-]{1,120}', parts[2])):
                raise ValueError('Media tool version response is invalid: ' + name)
            if self.digest(path) != before:
                raise ValueError('Media tool changed during identification: ' + name)
            self.paths[name] = str(path)
            self.evidence.append({'name': name, 'version': parts[2], 'executable_sha256': before})

    @staticmethod
    def digest(path):
        with Path(path).open('rb') as source:
            digest = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
            return digest.hexdigest()

    def verify(self):
        for item in self.evidence:
            if self.digest(self.paths[item['name']]) != item['executable_sha256']:
                raise ValueError('Media executable changed during production: ' + item['name'])


def portable_probe(probe):
    """Export technical media facts without source-authored tags or side data."""
    format_fields = {'filename', 'format_name', 'nb_streams', 'start_time',
                     'duration', 'size', 'bit_rate'}
    stream_fields = {'index', 'codec_name', 'codec_type', 'width', 'height',
                     'pix_fmt', 'sample_rate', 'channels', 'channel_layout',
                     'avg_frame_rate', 'r_frame_rate', 'time_base', 'start_time',
                     'duration', 'bit_rate', 'nb_frames', 'sample_aspect_ratio',
                     'display_aspect_ratio'}
    def select(value, fields):
        return {key: item for key, item in value.items()
                if key in fields and isinstance(item, (str, int, float))}
    return {'format': select(probe.get('format', {}), format_fields),
            'streams': [select(stream, stream_fields) for stream in probe.get('streams', [])]}
