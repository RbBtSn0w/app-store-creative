"""Offline PPO decisions, archived delivery binding and scoped reproduction."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import struct
import subprocess
import zlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
import app_store_creative as cli
from artifact_lifecycle import Lifecycle
import ppo_assessment as assessment
import ppo_experiment
from record_primitives import digest
from test_v2_workflow import create_mock_png


def metrics(remote='remote-B', status='Performing Better', lift=6, confidence=93):
    return {'treatment_id': remote, 'apple_status': status, 'unique_impressions': 10000,
            'conversion_rate_pct': 21.2, 'relative_lift_pct': lift, 'confidence_pct': confidence}


def screenshot(content, card):
    # Preserve image dimensions and attach a distinct PNG text chunk per synthetic card.
    payload = b'tEXt' + b'card\x00' + card.encode()
    chunk = struct.pack('>I', len(payload) - 4) + payload + struct.pack('>I', zlib.crc32(payload))
    return content[:-12] + chunk + content[-12:]


class DecisionTests(unittest.TestCase):
    def test_decision_table(self):
        better = metrics()
        worse = metrics('remote-C', 'Performing Worse', -4)
        pending = metrics('remote-C', 'Collecting Data', None, None)
        for rows, ended, threshold, expected in [
            ([better], True, 5, 'use-treatment'), ([better], False, 5, 'wait'),
            ([metrics(lift=5, confidence=90)], True, 5, 'use-treatment'),
            ([metrics(confidence=89.9)], True, 5, 'needs-review'),
            ([metrics(lift=-0.1)], True, 5, 'needs-review'), ([metrics(status='Unknown')], True, 5, 'needs-review'),
            ([worse], True, 5, 'keep-control'), ([metrics(lift=3)], True, 5, 'keep-control'),
            ([better, pending], True, 5, 'inconclusive'), ([better], True, None, 'inconclusive'),
            ([metrics(status='Likely to be Inconclusive')], False, 5, 'wait'),
            ([metrics(status='Likely to be Inconclusive')], True, 5, 'inconclusive'),
            ([better, metrics('remote-C')], True, 5, 'needs-review'),
            ([better, worse], True, 5, 'use-treatment'),
            ([dict(better, unique_impressions=0)], True, 5, 'inconclusive'),
        ]:
            with self.subTest(rows=rows, ended=ended, threshold=threshold):
                action, _, selected = assessment.decide(rows, ended, threshold)
                self.assertEqual(action, expected)
                self.assertEqual(selected, 'remote-B' if expected == 'use-treatment' else None)

    def test_immutable_record_concurrent_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'assessment.json'
            with mock.patch.object(assessment.os, 'link', side_effect=OSError('interrupted')):
                with self.assertRaisesRegex(OSError, 'interrupted'):
                    assessment.write_once(path, {'n': 1})
            self.assertEqual(list(path.parent.iterdir()), [])
            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(list(pool.map(lambda _: assessment.write_once(path, {'n': 1}), range(8))), [{'n': 1}] * 8)
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                assessment.write_once(path, {'n': 2})
            self.assertEqual(assessment.read(path), {'n': 1})


class AssessmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.scope = {'locales': ['en-US'], 'targets': ['iphone_6_9']}
        self.spec = {'platform': 'IOS', 'name': 'First screenshot', 'trafficProportion': 50,
                     'treatments': {'B': {'name': 'Search first', 'cardOrder': ['search', 'save']}},
                     'policy': dict(self.scope, testedChange='Swap the first two screenshots',
                                    minRelativeLiftPct=5, durationEstimateDays=31, estimateSource='Synthetic fixture')}
        self.config = {'project': {'id': 'demo', 'name': 'Demo', 'bundleId': 'example.demo',
                                   'appStoreId': '123', 'locales': ['en-US', 'fr-FR']},
                       'publishing': {'platform': 'IOS', 'version': '1.0'}, 'targets': ['iphone_6_9', 'ipad_13'],
                       'cards': [{'id': key, 'screenshot': 'capture.png'} for key in ('save', 'search')],
                       'archivePolicy': {'schema_version': 1, 'mediaMode': 'git'},
                       'artifactPolicy': {'schema_version': 1, 'mediaBudgetBytes': 1073741824},
                       'experiments': {'first': self.spec}}
        self.save('creative.config.json', self.config)

    def save(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def run_cli(self, *args):
        return cli.run(cli.build_parser().parse_args(['ppo', '--repo', str(self.root), *args]))

    def seal(self, config):
        # Synthetic PNGs enter the normal register → validate → approve → seal path.
        config = copy.deepcopy(config)
        config['targets'] = self.scope['targets']
        config['project']['locales'] = self.scope['locales']
        self.save('fixture-config.json', config)
        core = Lifecycle.from_configuration(self.root, self.root / 'fixture-config.json')
        run = core.start_run({'platform': 'IOS', 'version': '1.0'})
        attempt = core.start_attempt(run['id'], 'render', 'test')
        source = self.root / 'capture.png'
        registered = core.register(attempt['id'], source, 'source', logical_path=source.name)
        artifacts = []
        for card in config['cards']:
            name = f"en-US/iphone_6_9/{card['id']}.png"
            rendered = self.root / (card['id'] + '.png')
            rendered.write_bytes(screenshot(source.read_bytes(), card['id']))
            artifacts.append(core.register(attempt['id'], rendered, 'screenshot', inputs=[registered['id']], logical_path=name)['id'])
        core.finish_attempt(attempt['id'], 'succeeded')
        candidate = core.select(run['id'], artifacts)
        valid = core.validate_candidate(candidate['id'])
        self.assertEqual(valid['status'], 'PASS', valid)
        approved = core.approve_design(candidate['id'], valid['id'], 'test-owner', 'test-fixture:approved')
        return core.seal(candidate['id'], valid['id'], approved['id'])['id']

    def prepare_snapshot(self):
        create_mock_png(self.root / 'capture.png')
        original = self.seal(self.config)
        variant = self.seal(ppo_experiment.derive_treatment_config(self.config, 'first', 'B'))
        self.run_cli('handoff', '--experiment', 'first', '--baseline-delivery', original,
                     '--treatment-delivery', 'B:' + variant, '--output', 'handoff.json')
        self.run_cli('bind', '--handoff', 'handoff.json', '--app-id', '123', '--asc-experiment-id', 'asc-1',
                     '--treatment-id', 'B:remote-B', '--output', 'binding.json')
        raw = self.root / 'source.txt'
        raw.write_text('Synthetic App Analytics transcription')
        self.snapshot = {'schema_version': 1, 'source': raw.name, 'source_sha256': digest(raw),
                         'app_id': '123', 'experiment_id': 'asc-1', 'scope': self.scope,
                         'binding_sha256': digest(self.root / 'binding.json'), 'state': 'ended',
                         'baseline': 'original', 'observed_at': '2026-11-23T08:00:00Z',
                         'rows': [dict(metrics('original'), conversion_rate_pct=20, relative_lift_pct=None,
                                       apple_status='Original', confidence_pct=None), metrics()]}
        self.save('snapshot.json', self.snapshot)

    def assess(self, *args):
        return self.run_cli('assess', '--binding', 'binding.json', '--snapshot', 'snapshot.json',
                            '--handoff', 'handoff.json', *args)

    def test_plan_and_card_order(self):
        self.assertEqual(self.run_cli('plan', '--experiment', 'first')['preflight']['status'], 'ready')
        self.spec['treatments']['C'] = {'name': 'C'}
        self.spec['trafficProportion'] = 40
        p = self.spec['policy']
        for days, expected in [(90, 'ready'), (91, 'defer'), (None, 'needs-input')]:
            p['durationEstimateDays'] = days
            self.save('creative.config.json', self.config)
            result = self.run_cli('plan', '--experiment', 'first')['preflight']
            self.assertEqual((result['status'], result['per_treatment_pct'], result['control_pct']), (expected, 20, 60))
        self.spec['treatments']['B']['cardOrder'] = ['save', 'save']
        self.save('creative.config.json', self.config)
        with self.assertRaisesRegex(ValueError, 'permutation'):
            self.run_cli('plan', '--experiment', 'first')

    def test_handoff_separates_reorder_and_upload_by_display_type(self):
        self.spec['policy']['targets'] = self.config['targets']
        self.spec['treatments']['C'] = {'name': 'New headline', 'cardOrder': ['search', 'save'], 'cardOverrides': {'save': {'headline': 'New'}}}
        self.save('creative.config.json', self.config)
        plan = self.run_cli('handoff', '--experiment', 'first', '--treatment-delivery', 'C:capture-C',
                            '--treatment-delivery', 'B:order-B')['asc_execution_plan']
        self.assertIn('--v2 --app 123 --platform IOS', plan[0])
        uploads = [line for line in plan if 'screenshot-sets upload' in line]
        self.assertEqual(len(uploads), 2)
        self.assertTrue(any('--device-type IPHONE_69' in line and 'capture-C/media/en-US/iphone_6_9' in line for line in uploads))
        self.assertTrue(any('--device-type IPAD_PRO_3GEN_129' in line and 'capture-C/media/en-US/ipad_13' in line for line in uploads))

    def test_planned_track_and_capture_must_match_sealed_composition(self):
        source = self.root / 'capture.png'
        create_mock_png(source)
        initial = source.read_bytes()
        control = self.seal(self.config)
        source.write_bytes(screenshot(initial, 'different-capture'))
        treatment = self.seal(ppo_experiment.derive_treatment_config(self.config, 'first', 'B'))
        source.write_bytes(initial)
        for connected, reason in [(True, 'planned composition'), (False, 'planned screenshot inputs')]:
            self.config['connectedTrack'] = connected
            self.save('creative.config.json', self.config)
            name = f'handoff-{connected}.json'
            self.run_cli('handoff', '--experiment', 'first', '--baseline-delivery', control,
                         '--treatment-delivery', 'B:' + treatment, '--output', name)
            with self.assertRaisesRegex(ValueError, reason):
                self.run_cli('bind', '--handoff', name, '--app-id', '123', '--asc-experiment-id', 'asc-1',
                             '--treatment-id', 'B:remote-B', '--output', 'binding.json')

    def test_full_workflow_and_scoped_production(self):
        self.prepare_snapshot()
        self.assertEqual(self.assess('--output', 'assessment.json')['action'], 'use-treatment')
        remote_cwd = self.root / 'another-working-directory'
        remote_cwd.mkdir()
        process = subprocess.run([sys.executable, cli.__file__, 'ppo', 'assess', '--repo', str(self.root),
                                  '--handoff', 'handoff.json', '--binding', 'binding.json',
                                  '--snapshot', 'snapshot.json', '--json'], cwd=remote_cwd,
                                 check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(process.stdout), assessment.read(self.root / 'assessment.json'))
        result = self.run_cli('result', '--handoff', 'handoff.json', '--assessment', 'assessment.json', '--output', 'result.json')
        self.assertEqual(result['selected_treatment'], 'B')
        args = ['reproduce', '--experiment', 'first', '--result', 'result.json']
        before = set(self.root.rglob('*'))
        plan = self.run_cli(*args)
        self.assertEqual(before, set(self.root.rglob('*')))
        self.assertEqual(plan['scope']['planned_delivery_count'], 1)
        self.assertEqual(plan['screenshot_order'], ['search', 'save'])

        def render(root, config_path, output_dir, **kwargs):
            config = assessment.read(config_path)
            self.assertEqual(config['project']['locales'], ['en-US'])
            self.assertEqual(config['targets'], ['iphone_6_9'])
            items = []
            for card in config['cards']:
                name = f"en-US/iphone_6_9/{card['id']}.png"
                path = output_dir / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(screenshot((root / card['screenshot']).read_bytes(), card['id']))
                items.append({'name': name, 'path': str(path)})
            return {'status': 'PASS', 'artifacts': items}
        with mock.patch('export_engine.run_export', side_effect=render):
            produced = self.run_cli(*args, '--execute')
            repeated = self.run_cli(*args, '--execute')
        self.assertEqual(produced['config_path'], repeated['config_path'])
        self.assertNotEqual(produced['attempt_id'], repeated['attempt_id'])
        self.assertEqual(produced['status'], 'PASS', produced)
        self.assertEqual(len(produced['export']['artifacts']), 2)
        with mock.patch('export_engine.run_export', return_value={'status': 'PASS', 'artifacts': []}):
            with self.assertRaisesRegex(ValueError, 'differs from measured'):
                self.run_cli(*args, '--execute')
        (self.root / 'capture.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'inputs differ'):
            self.run_cli(*args)

    def test_mismatched_archive_and_recipe_drift(self):
        self.prepare_snapshot()
        self.assess('--output', 'assessment.json')
        self.run_cli('result', '--handoff', 'handoff.json', '--assessment', 'assessment.json', '--output', 'result.json')
        self.config['cards'][0]['headline'] = 'New untested copy'
        self.save('creative.config.json', self.config)
        self.assertEqual(self.assess()['action'], 'use-treatment')
        with self.assertRaisesRegex(ValueError, 'Current recipe'):
            self.run_cli('reproduce', '--experiment', 'first', '--result', 'result.json')
        h = assessment.read(self.root / 'handoff.json')
        media = Path(h['treatments'][0]['delivery_path']) / 'media/en-US/iphone_6_9/search.png'
        media.write_bytes(b'changed since handoff')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.assess()

    def test_ended_without_winner_records_decision_and_blocks_reproduction(self):
        self.prepare_snapshot()
        for status, lift, decision in [('Performing Worse', -3, 'keep-control'),
                                       ('Likely to be Inconclusive', None, 'inconclusive')]:
            self.snapshot['rows'][1] = metrics(status=status, lift=lift)
            self.save('snapshot.json', self.snapshot)
            self.assertEqual(self.assess('--output', decision + '.json')['action'], decision)
            out = decision + '-result.json'
            result = self.run_cli('result', '--handoff', 'handoff.json', '--assessment', decision + '.json', '--output', out)
            self.assertEqual(result['decision'], decision)
            with self.assertRaisesRegex(ValueError, 'selecting a treatment'):
                self.run_cli('reproduce', '--experiment', 'first', '--result', out)

    def test_binding_and_assessment_mutations_are_rejected(self):
        self.prepare_snapshot()
        self.assess('--output', 'assessment.json')
        self.run_cli('result', '--handoff', 'handoff.json', '--assessment', 'assessment.json', '--output', 'result.json')
        a = assessment.read(self.root / 'assessment.json')
        a['rows'][1]['relative_lift_pct'] = 99
        self.save('assessment.json', a)
        with self.assertRaisesRegex(ValueError, 'matching terminal'):
            self.run_cli('reproduce', '--experiment', 'first', '--result', 'result.json')
        b = assessment.read(self.root / 'binding.json')
        b['assets']['remote-B'].clear()
        self.save('binding.json', b)
        with self.assertRaisesRegex(ValueError, 'Binding differs'):
            self.assess()

    def test_draft_ids_and_scope_preflight(self):
        self.run_cli('handoff', '--experiment', 'first', '--output', 'draft.json')
        with self.assertRaisesRegex(ValueError, 'draft'):
            self.run_cli('bind', '--handoff', 'draft.json', '--app-id', '123', '--asc-experiment-id', 'experiment',
                         '--treatment-id', 'B:remote', '--output', 'binding.json')
        for key, value in [('locales', ['de-DE']), ('targets', ['ipad_fake']), ('minRelativeLiftPct', True)]:
            broken = copy.deepcopy(self.config)
            broken['experiments']['first']['policy'][key] = value
            self.save('creative.config.json', broken)
            with self.assertRaises(ValueError):
                self.run_cli('plan', '--experiment', 'first')
        self.spec['trafficProportion'] = 100
        self.save('creative.config.json', self.config)
        self.assertIn('no-original-traffic', self.run_cli('plan', '--experiment', 'first')['preflight']['reasons'])
        self.spec['policy']['anotherTestRunning'] = True
        self.save('creative.config.json', self.config)
        self.assertEqual(self.run_cli('plan', '--experiment', 'first')['preflight']['status'], 'defer')
        self.spec['treatments'].update({k: {'name': k} for k in ('C', 'D', 'E')})
        self.save('creative.config.json', self.config)
        with self.assertRaisesRegex(ValueError, 'at most three'):
            self.run_cli('plan', '--experiment', 'first')

    def test_snapshot_errors_and_terminal_gate(self):
        self.prepare_snapshot()
        self.snapshot['state'] = 'running'
        self.save('snapshot.json', self.snapshot)
        self.assertEqual(self.assess('--output', 'running.json')['action'], 'wait')
        with self.assertRaisesRegex(ValueError, 'terminal'):
            self.run_cli('result', '--handoff', 'handoff.json', '--assessment', 'running.json', '--output', 'result.json')
        for field, value in [('unique_impressions', True), ('unique_impressions', -1),
                             ('conversion_rate_pct', float('nan')), ('confidence_pct', 101)]:
            broken = copy.deepcopy(self.snapshot)
            broken['rows'][1][field] = value
            self.save('snapshot.json', broken)
            with self.assertRaises(ValueError):
                self.assess()
        for field, value in [('app_id', '456'), ('experiment_id', 'wrong'), ('observed_at', '2026-01-01'),
                             ('scope', {}), ('rows', self.snapshot['rows'] * 2)]:
            self.save('snapshot.json', dict(self.snapshot, **{field: value}))
            with self.assertRaises(ValueError):
                self.assess()
        self.save('snapshot.json', dict(self.snapshot, baseline='remote-B'))
        self.assertEqual(self.assess()['action'], 'needs-review')
        (self.root / 'source.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.assess()
