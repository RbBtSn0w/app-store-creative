#!/usr/bin/env python3
"""Merge JSON shard reports from run_sharded_tests.py into one Markdown summary.

The summary reads top-down: the verdict first, then failing tests, then the
per-shard table, with slow and skipped tests collapsed at the end. A shard that
produced no report (cancelled, timed out, or killed by the hang watchdog) is
shown explicitly instead of being silently omitted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

MESSAGE_LIMIT = 160
SLOWEST_COUNT = 10


def format_duration(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


def _cell(text: str) -> str:
    """Make text safe for a single Markdown table cell."""
    text = " ".join(text.split()).replace("|", "\\|")
    if len(text) > MESSAGE_LIMIT:
        text = text[: MESSAGE_LIMIT - 1] + "…"
    return text


def test_label(test_id: str) -> str:
    """Render `Class.method` with the module underneath, for compact table cells."""
    parts = test_id.split(".")
    if len(parts) < 3:
        return f"`{_cell(test_id)}`"
    module = ".".join(parts[:-2])
    return f"`{_cell('.'.join(parts[-2:]))}`<br><sub>{_cell(module)}</sub>"


def load_reports(report_dir: Path) -> list[dict]:
    reports = []
    if not report_dir.is_dir():
        return reports
    for path in sorted(report_dir.rglob("*.json")):
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            print(f"warning: skipping unreadable report {path}: {error}", file=sys.stderr)
    return reports


def render(
    reports: list[dict],
    expected_shards: int,
    source_url: str | None = None,
    run_url: str | None = None,
) -> str:
    by_shard = {report["shard"]: report for report in reports}
    missing = [shard for shard in range(1, expected_shards + 1) if shard not in by_shard]
    problems = [
        {**problem, "shard": report["shard"]}
        for report in reports
        for problem in report["problems"]
    ]
    skipped = [item for report in reports for item in report["skipped"]]
    tests_run = sum(report["tests_run"] for report in reports)
    # subTest failures can report one test several times, so clamp at zero.
    passed = max(0, tests_run - len(problems) - len(skipped))
    wall = 0.0
    if reports:
        start = min(report["started_at"] for report in reports)
        wall = max(report["started_at"] + report["elapsed"] for report in reports) - start

    ok = not problems and not missing
    lines = ["## ✅ Unit tests passed" if ok else "## ❌ Unit tests failed", ""]
    facts = []
    if problems:
        facts.append(f"**{len(problems):,} failed**")
    facts.append(f"**{passed:,} passed**" if ok else f"{passed:,} passed")
    facts.append(f"{len(skipped):,} skipped")
    facts.append(f"{len(reports)}/{expected_shards} shards reported")
    facts.append(f"{format_duration(wall)} wall time")
    lines += [" · ".join(facts), ""]

    if missing:
        names = ", ".join(f"{shard}/{expected_shards}" for shard in missing)
        hint = f" — [open the run]({run_url})" if run_url else ""
        lines += [
            f"> [!WARNING]\n> No report from shard {names}. It was cancelled, timed out, "
            f"or stopped by the hang watchdog; its job log names the test that was running{hint}.",
            "",
        ]

    if problems:
        lines += ["### Failing tests", "", "| Test | Location | Message |", "| --- | --- | --- |"]
        for problem in sorted(problems, key=lambda item: item["id"]):
            location = "—"
            if problem.get("file"):
                text = f"{problem['file']}:{problem['line']}"
                location = (
                    f"[`{text}`]({source_url}/{problem['file']}#L{problem['line']})"
                    if source_url
                    else f"`{text}`"
                )
            message = _cell(problem["message"])
            if problem["kind"] == "error":
                message = f"**Error:** {message}"
            lines.append(f"| {test_label(problem['id'])} | {location} | {message} |")
        lines.append("")

    lines += ["### Shards", "", "| Shard | Result | Tests | Skipped | Duration |",
              "| --- | --- | ---: | ---: | ---: |"]
    for shard in range(1, expected_shards + 1):
        report = by_shard.get(shard)
        if report is None:
            lines.append(f"| {shard}/{expected_shards} | ⚠️ No report | — | — | — |")
            continue
        failed = len(report["problems"])
        result = "✅ Passed" if not failed else f"❌ {failed} failed"
        lines.append(
            f"| {shard}/{expected_shards} | {result} | {report['tests_run']:,} "
            f"| {len(report['skipped']):,} | {format_duration(report['elapsed'])} |"
        )
    lines.append("")

    slowest = sorted(
        (
            (item["seconds"], item["id"], report["shard"])
            for report in reports
            for item in report["slowest"]
        ),
        reverse=True,
    )[:SLOWEST_COUNT]
    if slowest:
        lines += [
            f"<details><summary>Slowest {len(slowest)} tests</summary>",
            "",
            "| Duration | Test | Shard |",
            "| ---: | --- | ---: |",
        ]
        lines += [
            f"| {seconds:.1f}s | {test_label(test_id)} | {shard} |"
            for seconds, test_id, shard in slowest
        ]
        lines += ["", "</details>", ""]

    if skipped:
        reasons = Counter(_cell(item["reason"]) or "(no reason)" for item in skipped)
        lines += [
            f"<details><summary>Skipped tests by reason ({len(skipped):,})</summary>",
            "",
            "| Count | Reason |",
            "| ---: | --- |",
        ]
        lines += [f"| {count} | {reason} |" for reason, count in reasons.most_common()]
        lines += ["", "</details>", ""]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge shard reports into a job summary.")
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--shards", type=int, required=True)
    args = parser.parse_args()
    if args.shards < 1:
        parser.error(f"--shards must be >= 1, got {args.shards}")

    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("REPORT_SHA") or os.environ.get("GITHUB_SHA")
    run_id = os.environ.get("GITHUB_RUN_ID")
    source_url = f"{server}/{repository}/blob/{sha}" if server and repository and sha else None
    run_url = f"{server}/{repository}/actions/runs/{run_id}" if server and repository and run_id else None

    markdown = render(load_reports(args.report_dir), args.shards, source_url, run_url)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(markdown)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
