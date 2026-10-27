#!/usr/bin/env python3
"""Run a partitioned subset of test suites using standard library unittest.

Splits discovered test files deterministically across matrix runners.
Compatible with standard library unittest without third-party dependencies.

On GitHub Actions the runner also emits failure annotations; --report writes a
JSON shard report that .github/ci_test_report.py merges into one job summary.
A per-test watchdog dumps the stack of a hung test instead of letting the
job time out silently.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import re
import sys
import time
import unittest
from pathlib import Path

SLOWEST_COUNT = 10
_FRAME_PATTERN = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')


def discover_and_shard(
    tests_dir: Path,
    pattern: str,
    shard: int,
    total: int,
) -> list[Path]:
    """Find and return test files assigned to the given shard (1-indexed)."""
    all_files = sorted(tests_dir.glob(pattern))
    if not all_files:
        raise ValueError(f"No test files found in {tests_dir} matching {pattern}")
    return [f for idx, f in enumerate(all_files) if idx % total == (shard - 1)]


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def failure_location(traceback_text: str, repo_root: Path) -> tuple[str, int] | None:
    """Return the innermost repository frame of a traceback as (relative path, line)."""
    root = repo_root.resolve()
    location = None
    for match in _FRAME_PATTERN.finditer(traceback_text):
        path = Path(match["path"])
        try:
            relative = path.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        location = (relative.as_posix(), int(match["line"]))
    return location


def github_annotation(test_id: str, traceback_text: str, repo_root: Path) -> str:
    """Format a GitHub Actions ::error workflow command for a failed test."""
    message = failure_message(traceback_text)
    properties = [f"title={_escape_property(test_id)}"]
    location = failure_location(traceback_text, repo_root)
    if location:
        properties = [
            f"file={_escape_property(location[0])}",
            f"line={location[1]}",
            *properties,
        ]
    return f"::error {','.join(properties)}::{_escape_data(message)}"


def failure_message(traceback_text: str) -> str:
    """Return the final exception line of a traceback."""
    lines = [line.strip() for line in traceback_text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "Test failed"


def build_report(
    shard: int,
    total: int,
    result: "WatchdogResult",
    started_at: float,
    elapsed: float,
    repo_root: Path,
) -> dict:
    """Build the JSON shard report that ci_test_report.py merges into one summary."""
    problems = []
    for kind, entries in (("failure", result.failures), ("error", result.errors)):
        for test, traceback_text in entries:
            location = failure_location(traceback_text, repo_root)
            problems.append({
                "id": test.id(),
                "kind": kind,
                "message": failure_message(traceback_text),
                "file": location[0] if location else None,
                "line": location[1] if location else None,
            })
    slowest = sorted(result.test_durations.items(), key=lambda item: item[1], reverse=True)
    return {
        "shard": shard,
        "total": total,
        "started_at": started_at,
        "elapsed": elapsed,
        "tests_run": result.testsRun,
        "problems": problems,
        "skipped": [{"id": test.id(), "reason": str(reason)} for test, reason in result.skipped],
        "slowest": [
            {"id": test_id, "seconds": seconds} for test_id, seconds in slowest[:SLOWEST_COUNT]
        ],
    }


class WatchdogResult(unittest.TextTestResult):
    """Record per-test durations, and dump all thread stacks and exit when a
    single test exceeds the timeout."""

    test_timeout = 0.0

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.test_durations: dict[str, float] = {}
        self._test_started = 0.0

    def startTest(self, test: unittest.TestCase) -> None:
        super().startTest(test)
        self._test_started = time.monotonic()
        if self.test_timeout > 0:
            # buffer=True swaps sys.stderr for an in-memory stream, so dump to
            # the real stderr descriptor.
            faulthandler.dump_traceback_later(
                self.test_timeout, exit=True, file=sys.__stderr__
            )

    def stopTest(self, test: unittest.TestCase) -> None:
        faulthandler.cancel_dump_traceback_later()
        self.test_durations[test.id()] = time.monotonic() - self._test_started
        super().stopTest(test)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sharded Python unit tests.")
    parser.add_argument(
        "--shard",
        type=int,
        default=1,
        help="1-indexed shard number to execute (default: 1)",
    )
    parser.add_argument(
        "--total",
        type=int,
        default=1,
        help="Total number of shards (default: 1)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="test_*.py",
        help="Glob pattern for test files (default: 'test_*.py')",
    )
    parser.add_argument(
        "--test-timeout",
        type=float,
        default=300.0,
        help="Seconds a single test may run before its stack is dumped and the "
        "run aborts; 0 disables the watchdog (default: 300)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write a JSON shard report to this path",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Run tests in verbose mode",
    )
    args = parser.parse_args()

    if args.total < 1:
        parser.error(f"--total must be >= 1, got {args.total}")
    if args.shard < 1 or args.shard > args.total:
        parser.error(f"--shard must be between 1 and {args.total}, got {args.shard}")
    if args.test_timeout < 0:
        parser.error(f"--test-timeout must be >= 0, got {args.test_timeout}")

    repo_root = Path(__file__).resolve().parents[1]
    tests_dir = repo_root / "tests"
    runtime_dir = repo_root / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"

    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))
    if str(runtime_dir) not in sys.path:
        sys.path.insert(0, str(runtime_dir))

    shard_files = discover_and_shard(tests_dir, args.pattern, args.shard, args.total)
    total_files = len(sorted(tests_dir.glob(args.pattern)))

    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for file_path in shard_files:
        module_name = file_path.stem
        tests = loader.loadTestsFromName(module_name)
        suite.addTests(tests)

    print(
        f"[shard {args.shard}/{args.total}] Loaded {suite.countTestCases()} test cases "
        f"across {len(shard_files)}/{total_files} test files",
        flush=True,
    )

    WatchdogResult.test_timeout = args.test_timeout
    # buffer=True keeps output printed by passing tests out of the log, so only
    # failing tests show their captured stdout/stderr.
    runner = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1,
        buffer=True,
        resultclass=WatchdogResult,
    )
    started_at = time.time()
    start_time = time.monotonic()
    result = runner.run(suite)
    elapsed = time.monotonic() - start_time

    print(
        f"[shard {args.shard}/{args.total}] Completed in {elapsed:.2f}s "
        f"({'PASS' if result.wasSuccessful() else 'FAIL'})",
        flush=True,
    )

    if os.environ.get("GITHUB_ACTIONS") == "true":
        for test, traceback_text in [*result.failures, *result.errors]:
            print(github_annotation(test.id(), traceback_text, repo_root), flush=True)
    if args.report:
        report = build_report(args.shard, args.total, result, started_at, elapsed, repo_root)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
