"""Storage root resolution and workspace paths independent of lifecycle operations."""
from dataclasses import dataclass
from pathlib import Path


def overlaps(a, b):
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


STORAGE_DEFAULTS = {'workspaceRoot': '.creative', 'objectRoot': '.creative/objects',
                    'releaseRoot': 'creative-releases', 'publicationRoot': 'creative-publications'}


@dataclass(frozen=True)
class StoragePaths:
    project: Path
    workspace: Path
    objects: Path
    releases: Path
    publications: Path

    @classmethod
    def resolve(cls, root, config):
        root = Path(root).resolve()
        raw = config.get('storage', {})
        if not isinstance(raw, dict):
            raise ValueError('storage must be an object')
        defaults = STORAGE_DEFAULTS
        unknown = set(raw) - set(defaults)
        if unknown:
            raise ValueError(f'Unknown storage fields: {sorted(unknown)}')
        paths = []
        for key, default in defaults.items():
            value = raw.get(key, str(Path(raw.get('workspaceRoot', '.creative')) / 'objects') if key == 'objectRoot' else default)
            if not isinstance(value, str) or not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError(f'Invalid storage path: {key}')
            path = Path(value)
            resolved = (path if path.is_absolute() else root / path).resolve()
            if not path.is_absolute() and not resolved.is_relative_to(root):
                raise ValueError('External storage requires an explicit absolute path, not a relative escape')
            if resolved == root:
                raise ValueError('Storage cannot be the project root')
            if resolved == Path(resolved.anchor) or overlaps(resolved, root / '.git'):
                raise ValueError('Storage cannot contain repository metadata or filesystem root')
            paths.append(resolved)
        workspace, objects, releases, publications = paths
        if workspace == objects or (overlaps(workspace, objects) and not objects.is_relative_to(workspace)):
            raise ValueError('Storage overlap: workspace cannot be inside object root')
        for a, b in ((releases, publications), (releases, workspace), (releases, objects),
                     (publications, workspace), (publications, objects)):
            if overlaps(a, b):
                raise ValueError('Storage roots overlap')
        return cls(root, workspace, objects, releases, publications)

    def binding(self):
        return {key: str(getattr(self, key)) for key in ('workspace', 'objects', 'releases', 'publications')}

    @property
    def inputs(self) -> Path:
        return self.workspace / 'inputs'

    @property
    def pipeline(self) -> Path:
        return self.workspace / 'pipeline'

    @property
    def dist(self) -> Path:
        return self.workspace / 'dist'

    @property
    def cache(self) -> Path:
        return self.workspace / '.cache'

    @staticmethod
    def ensure_cache_isolation(cache_path: Path) -> Path:
        p = Path(cache_path)
        if p.is_symlink():
            raise ValueError('Symlinked cache directory')
        p.mkdir(parents=True, exist_ok=True)
        if p.is_symlink():
            raise ValueError('Symlinked cache directory')
        gitignore = p / '.gitignore'
        if gitignore.is_symlink():
            raise ValueError('Symlinked cache ignore file')
        if not gitignore.exists() or gitignore.read_text() != '*\n':
            gitignore.write_text('*\n')
        return p

    def ensure_layers(self) -> dict[str, Path]:
        """Ensure the RFC #46 4-layer workspace layout exists."""
        layers = {
            'inputs': self.inputs,
            'pipeline': self.pipeline,
            'dist': self.dist,
            'cache': self.cache,
        }
        for name, path in layers.items():
            path.mkdir(parents=True, exist_ok=True)
        self.ensure_cache_isolation(layers['cache'])
        return layers

    def layer_paths(self) -> dict[str, Path]:
        return {
            'inputs': self.workspace / 'inputs',
            'pipeline': self.workspace / 'pipeline',
            'dist': self.workspace / 'dist',
            'cache': self.workspace / '.cache',
        }

    def resolve_layer(self, name: str) -> Path:
        valid_layers = {'inputs', 'pipeline', 'dist', 'cache'}
        if name not in valid_layers:
            raise ValueError(f"Unknown workspace layer: {name}. Expected one of {sorted(valid_layers)}")
        if name == 'cache':
            return self.cache
        return getattr(self, name)
