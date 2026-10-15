"""Unit tests for sharded test runner (.github/run_sharded_tests.py)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = REPO_ROOT / ".github" / "run_sharded_tests.py"

sys.path.insert(0, str(REPO_ROOT / ".github"))
import run_sharded_tests  # noqa: E402


class ShardedTestRunnerTests(unittest.TestCase):
    def test_discover_and_shard_partitioning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            files = [test_dir / f"test_{i:02d}.py" for i in range(10)]
            for f in files:
                f.write_text("import unittest\n")

            shards = [
                run_sharded_tests.discover_and_shard(test_dir, "test_*.py", s, 3)
                for s in (1, 2, 3)
            ]

            # Shard counts for 10 files across 3 shards: 4, 3, 3
            self.assertEqual([len(s) for s in shards], [4, 3, 3])

            # Ensure all files are accounted for and there is no overlap
            flat_shards = [f for s in shards for f in s]
            self.assertEqual(len(flat_shards), 10)
            self.assertEqual(set(flat_shards), set(files))

    def test_discover_and_shard_empty_directory_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            with self.assertRaises(ValueError):
                run_sharded_tests.discover_and_shard(test_dir, "test_*.py", 1, 1)

    def test_discover_and_shard_single_shard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_dir = Path(tmp_dir)
            files = [test_dir / f"test_{i}.py" for i in range(5)]
            for f in files:
                f.write_text("import unittest\n")

            result = run_sharded_tests.discover_and_shard(test_dir, "test_*.py", 1, 1)
            self.assertEqual(result, sorted(files))

    def test_cli_argument_validation(self) -> None:
        invalid_args = [
            ["--shard", "0", "--total", "1"],
            ["--shard", "2", "--total", "1"],
            ["--shard", "1", "--total", "0"],
        ]
        for args in invalid_args:
            with self.subTest(args=args):
                proc = subprocess.run(
                    [sys.executable, str(RUNNER_SCRIPT), *args],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("error:", proc.stderr.lower())


if __name__ == "__main__":
    unittest.main()
