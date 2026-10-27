"""Unit tests for the combined CI test summary (.github/ci_test_report.py)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCRIPT = REPO_ROOT / ".github" / "ci_test_report.py"

sys.path.insert(0, str(REPO_ROOT / ".github"))
import ci_test_report  # noqa: E402


def shard_report(shard: int, **overrides) -> dict:
    report = {
        "shard": shard,
        "total": 2,
        "started_at": 1000.0 + shard,
        "elapsed": 60.0 * shard,
        "tests_run": 10,
        "problems": [],
        "skipped": [],
        "slowest": [{"id": f"test_mod.Case.test_{shard}", "seconds": float(shard)}],
    }
    report.update(overrides)
    return report


class FormattingTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(ci_test_report.format_duration(42.4), "42s")
        self.assertEqual(ci_test_report.format_duration(184.4), "3m 04s")

    def test_test_label_splits_class_method_from_module(self) -> None:
        self.assertEqual(
            ci_test_report.test_label("test_mod.Case.test_x"),
            "`Case.test_x`<br><sub>test_mod</sub>",
        )
        self.assertEqual(ci_test_report.test_label("setUpModule"), "`setUpModule`")

    def test_cell_escapes_pipes_newlines_and_truncates(self) -> None:
        self.assertEqual(ci_test_report._cell("a|b\nc"), "a\\|b c")
        long = ci_test_report._cell("x" * 500)
        self.assertEqual(len(long), ci_test_report.MESSAGE_LIMIT)
        self.assertTrue(long.endswith("…"))


class RenderTests(unittest.TestCase):
    def test_passing_run_leads_with_verdict_and_hides_failure_section(self) -> None:
        markdown = ci_test_report.render([shard_report(1), shard_report(2)], 2)
        self.assertTrue(markdown.startswith("## ✅ Unit tests passed"))
        self.assertIn("**20 passed** · 0 skipped · 2/2 shards reported · 2m 01s wall time", markdown)
        self.assertNotIn("Failing tests", markdown)
        self.assertNotIn("Skipped tests", markdown)
        self.assertIn("| 1/2 | ✅ Passed | 10 | 0 | 1m 00s |", markdown)

    def test_failures_come_before_shards_and_link_to_source(self) -> None:
        failing = shard_report(2, problems=[
            {"id": "test_mod.Case.test_a", "kind": "failure",
             "message": "AssertionError: 1 != 2", "file": "tests/test_mod.py", "line": 9},
            {"id": "test_mod.Case.test_b", "kind": "error",
             "message": "RuntimeError: x", "file": None, "line": None},
        ])
        markdown = ci_test_report.render(
            [shard_report(1), failing], 2, source_url="https://h/o/r/blob/abc"
        )
        self.assertTrue(markdown.startswith("## ❌ Unit tests failed"))
        self.assertIn("**2 failed** · 18 passed", markdown)
        self.assertLess(markdown.index("### Failing tests"), markdown.index("### Shards"))
        self.assertIn(
            "[`tests/test_mod.py:9`](https://h/o/r/blob/abc/tests/test_mod.py#L9)", markdown
        )
        self.assertIn("| — | **Error:** RuntimeError: x |", markdown)
        self.assertIn("| 2/2 | ❌ 2 failed |", markdown)

    def test_missing_shard_fails_verdict_with_warning(self) -> None:
        markdown = ci_test_report.render([shard_report(1)], 2, run_url="https://h/run/1")
        self.assertTrue(markdown.startswith("## ❌ Unit tests failed"))
        self.assertIn("1/2 shards reported", markdown)
        self.assertIn("No report from shard 2/2", markdown)
        self.assertIn("[open the run](https://h/run/1)", markdown)
        self.assertIn("| 2/2 | ⚠️ No report | — | — | — |", markdown)

    def test_slowest_and_skipped_are_collapsed_and_ordered(self) -> None:
        reports = [
            shard_report(1, skipped=[{"id": "a.B.c", "reason": "needs macOS"}] * 2),
            shard_report(2, skipped=[{"id": "a.B.d", "reason": "no ffmpeg"}]),
        ]
        markdown = ci_test_report.render(reports, 2)
        self.assertIn("<details><summary>Slowest 2 tests</summary>", markdown)
        self.assertLess(markdown.index("test_2"), markdown.index("test_1"))
        self.assertIn("<details><summary>Skipped tests by reason (3)</summary>", markdown)
        self.assertLess(markdown.index("| 2 | needs macOS |"), markdown.index("| 1 | no ffmpeg |"))


class CommandLineTests(unittest.TestCase):
    def test_writes_summary_from_report_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            reports = tmp_path / "reports"
            reports.mkdir()
            (reports / "shard-1.json").write_text(json.dumps(shard_report(1)))
            (reports / "broken.json").write_text("{")
            summary = tmp_path / "summary.md"
            proc = subprocess.run(
                [sys.executable, str(REPORT_SCRIPT), str(reports), "--shards", "1"],
                capture_output=True,
                text=True,
                env={"GITHUB_STEP_SUMMARY": str(summary)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("skipping unreadable report", proc.stderr)
            self.assertTrue(summary.read_text().startswith("## ✅ Unit tests passed"))

    def test_missing_report_directory_reports_every_shard_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            proc = subprocess.run(
                [sys.executable, str(REPORT_SCRIPT), str(Path(tmp_dir) / "none"), "--shards", "2"],
                capture_output=True,
                text=True,
                env={},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("0/2 shards reported", proc.stdout)


if __name__ == "__main__":
    unittest.main()
