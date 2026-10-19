"""Provenance audit report contract tests using sealed delivery fixtures."""
import json
from pathlib import Path
import re
import unittest

import test_delivery_lifecycle as fixtures


class AuditReportTests(fixtures.DeliveryLifecycleTests):
    def sealed(self):
        validation, approval = self.approved()
        return self.store.seal(self.candidate['id'], validation['id'], approval['id'])

    def test_report_contains_summary_and_public_surfaces(self):
        from audit_report import generate_report

        delivery = self.sealed()
        report = generate_report(self.store, self.run['id'])

        self.assertIn('# Provenance Audit Report', report)
        self.assertIn(f'**Run:** `{self.run["id"]}`', report)
        integrity = re.search(r'`artifacts=(\d+) receipts=(\d+) candidates=(\d+) '
                              r'approvals=(\d+) gaps=(\d+)`', report)
        self.assertIsNotNone(integrity)
        self.assertEqual(int(integrity.group(1)), 2)
        self.assertEqual(int(integrity.group(3)), 1)
        self.assertEqual(int(integrity.group(4)), 1)
        self.assertEqual(int(integrity.group(5)), 1)
        self.assertIn(f'`{delivery["id"]}`', report)
        self.assertIn('Status |', report)
        self.assertIn('PASS', report)
        self.assertIn('No publications recorded.', report)

    def test_missing_receipt_and_approval_are_explicit_gaps(self):
        from audit_report import generate_report

        report = generate_report(self.store, self.run['id'])
        self.assertIn('gaps=2', report)
        self.assertIn('No producer-evidence receipt in this run', report)
        self.assertIn('| receipt |', report)
        self.assertIn('| approval |', report)

    def test_missing_approval_is_an_explicit_gap(self):
        from audit_report import generate_report

        run = self.store.start_run({'version': '1.6', 'platform': 'MAC_OS'})
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        self.store.register(attempt['id'], self.root / 'source.png', 'source',
                            logical_path='source.png')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        report = generate_report(self.store, run['id'])
        self.assertIn('No design approvals recorded.', report)
        self.assertIn('No producer-evidence receipt in this run', report)

    def test_partial_artifact_is_an_explicit_gap(self):
        from audit_report import generate_report

        run = self.store.start_run({'version': '1.7', 'platform': 'MAC_OS'})
        attempt = self.store.start_attempt(run['id'], 'render', 'agent')
        self.store.register(attempt['id'], self.root / 'source.png', 'screenshot',
                            partial=True, logical_path='partial.png')
        self.store.finish_attempt(attempt['id'], 'succeeded')
        report = generate_report(self.store, run['id'])
        self.assertIn('partial-artifact', report)

    def test_cli_outputs_markdown(self):
        import subprocess
        import sys

        self.sealed()
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        (self.root / 'creative.config.json').write_text(json.dumps(self.config))
        process = subprocess.run(
            [sys.executable, str(cli), 'audit', '--repo', str(self.root), 'report', '--run-id', self.run['id']],
            capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('# Provenance Audit Report', process.stdout)


if __name__ == '__main__':
    unittest.main()
