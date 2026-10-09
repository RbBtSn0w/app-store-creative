"""Descriptor-bound staging that never cleans substituted owner files."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import secrets
import stat


def identity(info):
    return info.st_dev, info.st_ino


class StagedFile:
    def __init__(self, directory, descriptor, name, stream):
        self.directory = directory
        self.descriptor = descriptor
        self.name = name
        self.stream = stream
        self.directory_identity = identity(os.fstat(descriptor))
        self.file_identity = identity(os.fstat(stream.fileno()))

    def check_directory(self):
        if (self.directory.resolve() != self.directory
                or identity(self.directory.lstat()) != self.directory_identity):
            raise ValueError('Staging directory identity changed')

    def sync(self):
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def inspect(self):
        self.check_directory()
        self.sync()
        self.stream.seek(0)
        sha = hashlib.file_digest(self.stream, 'sha256').hexdigest()
        return sha, os.fstat(self.stream.fileno()).st_size

    def publish(self, destination):
        destination = Path(destination)
        self.check_directory()
        current = os.stat(self.name, dir_fd=self.descriptor, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or identity(current) != self.file_identity:
            raise ValueError('Staged file identity changed')
        if not destination.is_absolute() or destination.resolve() != destination:
            raise ValueError('Staged destination contains aliases')
        parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if (destination.parent.resolve() != destination.parent
                    or identity(destination.parent.lstat()) != identity(os.fstat(parent))):
                raise ValueError('Staged destination parent changed')
            os.link(self.name, destination.name, src_dir_fd=self.descriptor,
                    dst_dir_fd=parent, follow_symlinks=False)
            os.fsync(parent)
        finally:
            os.close(parent)


@contextmanager
def staged_file(directory):
    directory = Path(directory)
    if not directory.is_absolute() or directory.resolve() != directory:
        raise ValueError('Staging directory contains aliases')
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = '.creative-object-' + secrets.token_hex(16)
    stream = None
    expected = None
    try:
        if directory.resolve() != directory or identity(directory.lstat()) != identity(os.fstat(parent)):
            raise ValueError('Staging directory identity changed')
        descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        stream = os.fdopen(descriptor, 'w+b')
        expected = identity(os.fstat(stream.fileno()))
        yield StagedFile(directory, parent, name, stream)
    finally:
        try:
            if stream is not None:
                stream.close()
            if expected is not None:
                try:
                    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if identity(current) == expected:
                        os.unlink(name, dir_fd=parent)
        finally:
            os.close(parent)
