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
            return hashlib.file_digest(source, 'sha256').hexdigest()

    def verify(self):
        for item in self.evidence:
            if self.digest(self.paths[item['name']]) != item['executable_sha256']:
                raise ValueError('Media executable changed during production: ' + item['name'])
