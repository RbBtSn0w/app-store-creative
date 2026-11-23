"""Repeat-release planning, rendered evidence and recorded experiment decisions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_delivery_lifecycle as fixtures
from app_store_creative import build_parser, run
from ppo_experiment import compile_ppo_handoff
from test_ppo_experiment import SAMPLE_CONFIG
from studio_server import StudioRequestHandler


class ReleaseReviewTests(unittest.TestCase):
    setUp = fixtures.DeliveryLifecycleTests.setUp
    approved = fixtures.DeliveryLifecycleTests.approved

    def invoke(self, *args):
        return run(build_parser().parse_args(list(args)))

    def test_experiment_result_is_bound_and_write_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'creative.config.json').write_text(json.dumps(SAMPLE_CONFIG))
            compile_ppo_handoff(root, SAMPLE_CONFIG, 'visual_style_cro', 'old',
                                {'quartz_titanium': 'new'}, root / 'handoff.json')
            args = ('ppo', '--repo', folder, 'result', '--handoff', 'handoff.json', '--output', 'outcome.json',
                    '--decision', 'inconclusive', '--market', 'US', '--change', 'Opening image',
                    '--observation', 'Insufficient traffic', '--evidence', 'review-01')
            result = self.invoke(*args)
            self.assertIsNone(result['selected_delivery'])
            self.assertEqual(result['control_delivery'], 'old')
            self.assertEqual(result, json.loads((root / 'outcome.json').read_text()))
            with self.assertRaises(FileExistsError):
                self.invoke(*args)
            with self.assertRaisesRegex(ValueError, 'named treatment'):
                self.invoke(*args, '--treatment', 'quartz_titanium')

            winner = list(args)
            winner[winner.index('inconclusive')] = 'use-treatment'
            winner[winner.index('outcome.json')] = 'winner.json'
            self.invoke(*winner, '--treatment', 'quartz_titanium')
            reproduce = ('ppo', '--repo', folder, 'reproduce', '--experiment', 'visual_style_cro', '--result')
            self.assertEqual(self.invoke(*reproduce, 'winner.json')['provenance']['variant_id'], 'quartz_titanium')
            with self.assertRaisesRegex(ValueError, 'selecting a treatment'):
                self.invoke(*reproduce, 'outcome.json')
