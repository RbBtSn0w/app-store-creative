"""Unit tests for TASK-202: RFC #46 4-Layer Workspace & Cache Isolation (Issue #46)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))

from artifact_lifecycle import StoragePaths, Lifecycle


class WorkspaceLayersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {
            "project": {"id": "demo", "name": "Demo", "bundleId": "example.demo", "locales": ["en-US"]},
            "targets": ["mac_16_10"],
            "cards": [{"id": "hero"}],
            "storage": {"workspaceRoot": ".creative"},
        }

    def test_layer_paths_properties_and_resolution(self):
        paths = StoragePaths.resolve(self.root, self.config)
        self.assertEqual(paths.inputs, paths.workspace / "inputs")
        self.assertEqual(paths.pipeline, paths.workspace / "pipeline")
        self.assertEqual(paths.dist, paths.workspace / "dist")
        self.assertEqual(paths.cache, paths.workspace / ".cache")

        self.assertEqual(paths.resolve_layer("inputs"), paths.inputs)
        self.assertEqual(paths.resolve_layer("pipeline"), paths.pipeline)
        self.assertEqual(paths.resolve_layer("dist"), paths.dist)
        self.assertEqual(paths.resolve_layer("cache"), paths.cache)
        self.assertFalse(paths.cache.exists(), "Accessing cache property must be a pure getter without disk side-effects")

        with self.assertRaisesRegex(ValueError, "Unknown workspace layer"):
            paths.resolve_layer("invalid_layer")

    def test_ensure_layers_creates_directories_and_cache_gitignore(self):
        paths = StoragePaths.resolve(self.root, self.config)
        layers = paths.ensure_layers()

        for name, layer_path in layers.items():
            self.assertTrue(layer_path.is_dir(), f"Layer {name} directory must exist")

        gitignore = paths.workspace / ".cache" / ".gitignore"
        self.assertTrue(gitignore.is_file(), ".cache/.gitignore must be created")
        self.assertEqual(gitignore.read_text(), "*\n")

    def test_ensure_cache_isolation_rejects_symlinks(self):
        target = self.root / "real_dir"
        target.mkdir()
        symlink_dir = self.root / "sym_cache"
        symlink_dir.symlink_to(target)

        with self.assertRaisesRegex(ValueError, "Symlinked cache directory"):
            StoragePaths.ensure_cache_isolation(symlink_dir)

        cache_dir = self.root / "cache_with_sym_ignore"
        cache_dir.mkdir()
        symlink_ignore = cache_dir / ".gitignore"
        symlink_ignore.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Symlinked cache ignore file"):
            StoragePaths.ensure_cache_isolation(cache_dir)

    def test_cache_gitignore_injection_on_workspace_transaction(self):
        store = Lifecycle(self.root, self.config)
        run = store.start_run({"version": "1.0", "platform": "MAC_OS"})
        self.assertTrue(run["id"])

        cache_dir = store.paths.workspace / ".cache"
        self.assertTrue(cache_dir.is_dir())
        gitignore = cache_dir / ".gitignore"
        self.assertTrue(gitignore.is_file())
        self.assertEqual(gitignore.read_text(), "*\n")

    def test_git_status_remains_clean_with_cache_artifacts(self):
        # Initialize a git repo at root
        subprocess.run(["git", "-C", str(self.root), "init", "--quiet"], check=True)
        store = Lifecycle(self.root, self.config)
        store.start_run({"version": "1.0", "platform": "MAC_OS"})

        # Put dummy artifacts inside .cache
        cache_dir = store.paths.workspace / ".cache"
        (cache_dir / "temp_render_frame.raw").write_bytes(b"dummy frame bytes")
        (cache_dir / "chromium_profile").mkdir(parents=True, exist_ok=True)
        (cache_dir / "chromium_profile/cache.bin").write_bytes(b"cache data")

        # Check git status: untracked files should not include anything inside .cache
        result = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain", "-uall"],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            self.assertNotIn(".creative/.cache/temp_render_frame.raw", line)
            self.assertNotIn(".creative/.cache/chromium_profile", line)


if __name__ == "__main__":
    unittest.main()
