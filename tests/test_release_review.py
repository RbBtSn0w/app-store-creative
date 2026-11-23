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

    def test_opening_proposals_survive_config_roundtrip_and_reject_duplicate_ids(self):
        from studio_contract import check_config
        proposals = [{'audience': 'Writers', 'benefit': 'Reuse the last reply', 'cardIds': ['hero']},
                     {'audience': 'Researchers', 'benefit': 'Retrieve a source', 'cardIds': ['archived-card']}]
        self.config['studio'] = {'openings': proposals}
        loaded = check_config(json.loads(json.dumps(self.config)))
        self.assertEqual(loaded['studio']['openings'], proposals)
        proposals[1]['cardIds'] = ['hero', 'hero']
        with self.assertRaisesRegex(ValueError, 'distinct card IDs'):
            check_config(self.config)

    def test_compare_before_and_after_export_and_preserve_stale_guard(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.store.config_path.write_text(json.dumps(self.config))
        plan = ('delivery', '--repo', str(self.root), 'screenshot-plan', '--id', delivery['id'])
        compare = ('candidate', '--repo', str(self.root), 'compare', '--id', self.candidate['id'],
                   '--baseline-delivery', delivery['id'])
        self.assertEqual(self.invoke(*plan)['assets'][0]['reasons'], [])
        self.assertEqual(self.invoke(*compare)['assets'][0]['reasons'], [])
        self.config['project']['locales'].append('zh-Hans')
        self.config['localizations'] = {'zh-Hans': {'hero': {'headline': '搜索', 'screenshot': 'source.png'}}}
        self.store.config_path.write_text(json.dumps(self.config))
        rows = self.invoke(*plan)['assets']
        self.assertEqual(rows[0]['reasons'], [])
        self.assertIn('New placement', rows[1]['reasons'])
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            self.invoke(*compare)
        (self.root / 'source.png').write_bytes(b'changed capture, same filename')
        self.assertIn('Capture changed', self.invoke(*plan)['assets'][0]['reasons'])
        (self.root / 'source.png').unlink()
        self.assertIn('Capture unavailable', self.invoke(*plan)['assets'][0]['reasons'])

    def test_plan_accepts_production_platform_when_targets_are_omitted(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.config.pop('targets', None)
        self.config.pop('publishing', None)
        self.store.config_path.write_text(json.dumps(self.config))
        plan = self.invoke('delivery', '--repo', str(self.root), 'screenshot-plan', '--id', delivery['id'])
        self.assertEqual(plan['baseline_id'], delivery['id'])

    def test_studio_routes_use_the_selected_baseline_and_capture(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.store.config_path.write_text(json.dumps(self.config))
        handler = object.__new__(StudioRequestHandler)
        handler.repo_root = self.root
        handler.config_path = self.store.config_path
        handler._local_request = Mock(return_value=True)
        handler._json = Mock()
        handler.path = '/api/deliveries/' + delivery['id'] + '/screenshot-plan'
        handler.do_GET()
        self.assertEqual(handler._json.call_args.args[0]['baseline_id'], delivery['id'])
        handler.path = '/api/candidates/' + self.candidate['id'] + '/compare?baseline=' + delivery['id']
        handler.do_GET()
        self.assertEqual(handler._json.call_args.args[0]['candidate_id'], self.candidate['id'])
        handler.path = '/api/capture-copy?locale=en-US&target=mac_16_10&card=hero&phrase=Copy'
        with patch('subprocess.run', return_value=Mock(returncode=0, stdout='[]')):
            handler.do_GET()
        self.assertEqual(handler._json.call_args.args[0]['matches'], [])
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='Vision unavailable')):
            handler.do_GET()
        self.assertEqual(handler._json.call_args.args[1], 400)
        self.assertIn('Vision unavailable', handler._json.call_args.args[0]['error'])

    def test_relocated_equal_capture_does_not_require_new_screenshot(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        self.config['cards'][0]['screenshot'] = 'moved.png'
        (self.root / 'source.png').rename(self.root / 'moved.png')
        self.store.config_path.write_text(json.dumps(self.config))
        plan = self.invoke('delivery', '--repo', str(self.root), 'screenshot-plan', '--id', delivery['id'])
        self.assertEqual(plan['assets'][0]['reasons'], [])

    def test_candidate_review_reports_video_poster_and_removed_screenshot_separately(self):
        validation, approval = self.approved()
        delivery = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        run_record = self.store.start_run({'platform': 'MAC_OS', 'version': '1.6'})
        attempt = self.store.start_attempt(run_record['id'], 'render', 'agent')
        ids = []
        for role, path in [('preview', 'zh-Hans/preview/app_preview.mp4'), ('poster', 'zh-Hans/preview/poster.png')]:
            record = self.store.register(attempt['id'], self.root / 'source.png', role, logical_path=path)
            ids.append(record['id'])
        self.store.finish_attempt(attempt['id'], 'succeeded')
        candidate = self.store.select(run_record['id'], ids)
        report = self.store.compare_candidate(candidate['id'], delivery['id'])
        rows = {row['role']: row for row in report['assets']}
        self.assertEqual(rows['screenshot']['reasons'], ['Absent from candidate'])
        self.assertFalse(rows['screenshot']['present'])
        for role in ('poster', 'preview'):
            self.assertEqual(rows[role]['reasons'], ['Added to candidate'])
            self.assertTrue(rows[role]['present'])

    def test_archive_comparison_verifies_media_independently_of_current_project(self):
        import shutil
        validation, approval = self.approved()
        release = self.store.seal(self.candidate['id'], validation['id'], approval['id'])
        archive = Path(release['local_path'])
        copy = self.root / 'archived-copy'
        shutil.copytree(archive, copy)
        args = ('archive', '--repo', str(self.root), 'compare', '--baseline', str(archive), '--path', copy.name)
        self.assertEqual(self.invoke(*args)['assets'][0]['reasons'], [])
        next((copy / 'media').rglob('*.png')).write_bytes(b'changed media')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.invoke(*args)
