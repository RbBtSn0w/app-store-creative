"""Unit tests for sharded test runner (.github/run_sharded_tests.py)."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_cli_rejects_negative_test_timeout(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(RUNNER_SCRIPT), "--test-timeout", "-1"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--test-timeout", proc.stderr)


def _traceback(*frames: tuple[str, int], last_line: str) -> str:
    body = "".join(f'  File "{path}", line {line}, in test\n    code\n' for path, line in frames)
    return f"Traceback (most recent call last):\n{body}{last_line}\n"


class _Case(unittest.TestCase):
    def test_example(self) -> None:
        pass


class GitHubReportingTests(unittest.TestCase):
    def test_failure_location_uses_innermost_repository_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            text = _traceback(
                (str(root / "tests" / "test_a.py"), 12),
                (str(root / "scripts" / "lib.py"), 40),
                ("/usr/lib/python3/unittest/case.py", 99),
                last_line="AssertionError: boom",
            )
            self.assertEqual(
                run_sharded_tests.failure_location(text, root), ("scripts/lib.py", 40)
            )

    def test_failure_location_without_repository_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            text = _traceback(("/elsewhere/x.py", 3), last_line="ValueError: x")
            self.assertIsNone(run_sharded_tests.failure_location(text, Path(tmp_dir)))

    def test_github_annotation_points_at_file_and_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            text = _traceback(
                (str(root / "tests" / "test_a.py"), 7),
                last_line="AssertionError: 50% done, a:b",
            )
            annotation = run_sharded_tests.github_annotation(
                "test_a.Case.test_x", text, root
            )
            self.assertEqual(
                annotation,
                "::error file=tests/test_a.py,line=7,title=test_a.Case.test_x"
                "::AssertionError: 50%25 done, a:b",
            )

    def test_github_annotation_without_location(self) -> None:
        annotation = run_sharded_tests.github_annotation(
            "mod.Case.test_y", "", Path("/nonexistent")
        )
        self.assertEqual(annotation, "::error title=mod.Case.test_y::Test failed")

    def test_build_report_records_problems_skips_and_slowest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            result = run_sharded_tests.WatchdogResult(
                unittest.runner._WritelnDecorator(io.StringIO()), True, 0
            )
            case = _Case("test_example")
            result.testsRun = 3
            result.failures.append((
                case,
                _traceback((str(root / "tests" / "t.py"), 4), last_line="AssertionError: no"),
            ))
            result.errors.append((case, "RuntimeError: boom\n"))
            result.skipped.append((case, "needs macOS"))
            result.test_durations = {"a.B.fast": 0.1, "a.B.slow": 3.0}
            report = run_sharded_tests.build_report(2, 4, result, 100.0, 12.5, root)
        self.assertEqual(report["shard"], 2)
        self.assertEqual(report["tests_run"], 3)
        self.assertEqual(report["problems"][0], {
            "id": case.id(), "kind": "failure", "message": "AssertionError: no",
            "file": "tests/t.py", "line": 4,
        })
        self.assertEqual(report["problems"][1]["kind"], "error")
        self.assertIsNone(report["problems"][1]["file"])
        self.assertEqual(report["skipped"], [{"id": case.id(), "reason": "needs macOS"}])
        self.assertEqual([item["id"] for item in report["slowest"]], ["a.B.slow", "a.B.fast"])
        json.dumps(report)


class WatchdogResultTests(unittest.TestCase):
    def test_watchdog_arms_per_test_and_cancels(self) -> None:
        result = run_sharded_tests.WatchdogResult(
            unittest.runner._WritelnDecorator(io.StringIO()), True, 0
        )
        case = _Case("test_example")
        with mock.patch.object(run_sharded_tests.WatchdogResult, "test_timeout", 5.0), \
                mock.patch.object(run_sharded_tests.faulthandler, "dump_traceback_later") as arm, \
                mock.patch.object(run_sharded_tests.faulthandler, "cancel_dump_traceback_later") as cancel:
            result.startTest(case)
            result.stopTest(case)
        arm.assert_called_once_with(5.0, exit=True, file=sys.__stderr__)
        cancel.assert_called_once_with()
        self.assertIn(case.id(), result.test_durations)

    def test_watchdog_disabled_at_zero(self) -> None:
        result = run_sharded_tests.WatchdogResult(
            unittest.runner._WritelnDecorator(io.StringIO()), True, 0
        )
        case = _Case("test_example")
        with mock.patch.object(run_sharded_tests.WatchdogResult, "test_timeout", 0.0), \
                mock.patch.object(run_sharded_tests.faulthandler, "dump_traceback_later") as arm:
            result.startTest(case)
            result.stopTest(case)
        arm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
