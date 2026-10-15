#!/usr/bin/env python3
"""Run a partitioned subset of test suites using standard library unittest.

Splits discovered test files deterministically across matrix runners.
Compatible with standard library unittest without third-party dependencies.
"""

from __future__ import annotations

import argparse
import sys
import time
import unittest
from pathlib import Path


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

    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    start_time = time.monotonic()
    result = runner.run(suite)
    elapsed = time.monotonic() - start_time

    print(
        f"[shard {args.shard}/{args.total}] Completed in {elapsed:.2f}s "
        f"({'PASS' if result.wasSuccessful() else 'FAIL'})",
        flush=True,
    )

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
