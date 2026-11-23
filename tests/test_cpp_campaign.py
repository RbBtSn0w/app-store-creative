"""CPP entry-point, sealed publication scope, reconciliation and reporting regressions."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_v2_workflow import cli, create_mock_png
from asc_observation_adapter import media_response
from cpp_campaign import compile_plan
from publication_lifecycle import check_remote_target, publication_assets


class CustomPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.base = self.root / '.creative/cpp/share-save'
        self.base.mkdir(parents=True)
        self.release = self.root / 'release.txt'
        self.release.write_text('iOS release acceptance: import shared text, find by search.')
        self.shot = self.root / 'share.png'
        create_mock_png(self.shot)
        self.brief = dict(schemaVersion=1, campaignKey='share-save', appId='123', bundleId='example.clip',
                          platform='ios', audience='Readers', channel='tutorial', intent='Save text',
                          locales=['en-US'], targets=['iphone_6_9'], releaseEvidence=self.ref(self.release))
        self.loc = dict(media={'iphone_6_9': ['share']}, promotionalText='Save text', keywords=['save'])
        self.proposal = dict(schemaVersion=1, decision='createPage', name='Share Save',
                             rationale='The tutorial needs a dedicated link', localizations={'en-US': self.loc},
                             claims=[{'text': 'Save text', 'evidenceRefs': ['acceptance']}])
        self.stock = dict(schemaVersion=1, appId='123', bundleId='example.clip', complete=True,
                          observedAt='2026-01-01T09:30:00Z', pages=[], approvedKeywords={'en-US': ['save']},
                          assets={'share': {**self.ref(self.shot), 'locale': 'en-US', 'target': 'iphone_6_9',
                                            'role': 'screenshot', 'artifactId': 'shot1'}},
                          defaultPage={'localizations': {'en-US': self.loc}},
                          evidence={'acceptance': {**self.ref(self.release), 'supports': ['Save text'],
                                                   'releaseSha256': self.ref(self.release)['sha256']}})
        self.save()

    def ref(self, path):
        return dict(path=str(path.relative_to(self.root)), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def save(self):
        for name, value in [('brief', self.brief), ('proposal', self.proposal), ('inventory', self.stock)]:
            (self.base / (name + '.json')).write_text(json.dumps(value))

    def run_cli(self, action, *args):
        opts = cli.build_parser().parse_args(['cpp', '--repo', str(self.root), action,
                                              '--campaign', 'share-save', *args])
        return cli.run(opts)

    def plan_file(self):
        result = self.run_cli('plan')
        (self.root / 'plan.json').write_text(json.dumps(result))
        return result

    def observation(self, plan):
        self.snapshot = dict(appId='123', bundleId='example.clip',
                             page={'pageId': 'P', 'name': 'Share Save', 'visible': True, 'approved': True,
                                   'url': 'https://apps.apple.com/us/app/id123?ppid=P'},
                             version={'pageId': 'P', 'pageVersionId': 'V', 'state': 'PREPARE_FOR_SUBMISSION',
                                      'localizations': {'en-US': {'localizationId': 'L', 'pageVersionId': 'V',
                                                                  'promotionalText': '', 'keywords': [], 'media': {}}}})
        self.observe(plan)

    def observe(self, plan):
        raw = self.root / 'asc.json'
        raw.write_text(json.dumps(self.snapshot))
        obs = dict(appId='123', bundleId='example.clip', campaignKey='share-save', pageId='P',
                   pageVersionId='V', observedAt='2026-01-01T09:30:00Z',
                   evidence=self.ref(raw), planDigest=plan['planDigest'])
        (self.base / 'observation.json').write_text(json.dumps(obs))

    def handoff(self, filename='out.json'):
        return self.run_cli('handoff', '--plan', 'plan.json', '--out', filename)

    def test_create_reconcile_and_repeat(self):
        plan = self.plan_file()
        self.assertEqual(plan['status'], 'ready')
        self.assertEqual(self.handoff()['operations'][0]['kind'], 'preparePage')
        self.assertEqual(self.handoff()['phase'], 'resolveDraft')
        result = self.run_cli('preview', '--plan', 'plan.json', '--out', 'review')
        self.assertIn('<img', Path(result['path']).read_text())
        self.observation(plan)
        ops = self.handoff('bound.json')['operations']
        self.assertEqual([o['kind'] for o in ops], ['updateText', 'replaceKeywords', 'reconcileMedia'])
        target = ops[-1]['scope']
        check_remote_target(target, {'target': {'platform': 'IOS'}}, {'project': {'bundleId': 'example.clip'}})
        asset = dict(role='screenshot', path='media/en-US/iphone_6_9/share.png',
                     artifact_id='shot1', sha256=self.ref(self.shot)['sha256'])
        self.assertEqual(publication_assets({'assets': [asset]}, {}, target=target), [asset])
        loc = self.snapshot['version']['localizations']['en-US']
        loc.update(promotionalText='Save text', keywords=['save'], media={'iphone_6_9': [asset['sha256']]})
        self.observe(plan)
        self.assertEqual(self.handoff('processed.json')['phase'], 'verifyMedia')
        loc['readiness'] = {'iphone_6_9': {asset['sha256']: dict(upload=True, processing=True, media=True)}}
        self.observe(plan)
        final = self.handoff('ready.json')
        self.assertEqual((final['phase'], final['operations']), ('reviewHandoff', []))

    def test_read_only_decisions(self):
        page = dict(pageId='P', name='Existing', approved=True, visible=True,
                    url='https://apps.apple.com/app/id123?ppid=P', localizations={'en-US': self.loc})
        self.stock['pages'] = [page]
        for decision in ['reuseDefault', 'reusePage', 'updatePage', 'needsEvidence']:
            with self.subTest(decision=decision):
                self.proposal['decision'] = decision
                self.proposal['pageId'] = 'P' if decision in ('reusePage', 'updatePage') else None
                self.save()
                result = self.run_cli('plan')
                self.assertEqual(result['decision'], decision)
                if decision.startswith('reuse'):
                    self.assertTrue(result['url'].startswith('https://apps.apple.com/'))
                self.assertEqual(result['status'], 'blocked' if decision == 'needsEvidence' else 'ready')

    def test_review_lock_and_page_visibility(self):
        plan = self.plan_file()
        self.observation(plan)
        self.snapshot['version']['state'] = 'IN_REVIEW'
        self.snapshot['page']['visible'] = False
        self.observe(plan)
        result = self.handoff()
        self.assertEqual(result['operations'], [])
        self.assertIsNone(result['url'])
        self.assertEqual(result['phase'], 'observe')

    def test_scope_rejection(self):
        plan = self.plan_file()
        self.observation(plan)
        self.snapshot['version']['localizations']['en-US']['pageVersionId'] = 'another'
        self.observe(plan)
        with self.assertRaisesRegex(ValueError, 'relationship'):
            self.handoff()
        with self.assertRaisesRegex(ValueError, 'Unknown or mixed'):
            check_remote_target(dict(platform='IOS', version_id='app-version', page_id='P'), {})
        with self.assertRaisesRegex(ValueError, 'localization'):
            media_response({'target': {'kind': 'customProductPageVersion', 'cpp_localization_id': 'L'}},
                           {'versionLocalizationId': 'L'}, {'localization_id': 'L'})

    def test_hash_change_and_stale_plan(self):
        self.plan_file()
        self.proposal['rationale'] += ' changed'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.handoff()
        self.shot.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Changed input'):
            self.run_cli('plan')

    def test_evidence_quota_keywords_and_pagination(self):
        self.stock.update(complete=False, approvedKeywords={}, pages=[{'pageId': str(n)} for n in range(70)])
        self.stock['evidence']['acceptance']['supports'] = ['Share out']
        self.proposal['deepLink'] = 'https://example.com/save'
        self.save()
        result = self.plan_file()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(len(result['blockers']), 5)
        self.assertEqual(self.handoff()['status'], 'blocked')
        self.assertFalse((self.root / 'out.json').exists())

    def test_cross_repo_and_cli_options(self):
        actual = self.run_cli('plan')
        args = cli.build_parser().parse_args(['cpp', 'plan', '--repo', str(self.root), '--campaign', 'share-save'])
        self.assertEqual(cli.run(args), actual)
        with self.assertRaisesRegex(ValueError, 'campaign key'):
            compile_plan(self.root, '../bad')
        self.stock['assets']['share']['path'] = '../outside'
        self.save()
        with self.assertRaisesRegex(ValueError, 'outside project'):
            self.run_cli('plan')

    def test_report_revisions_and_zero_vs_missing(self):
        self.observation(self.plan_file())
        cols = 'Date\tApp Apple Identifier\tPage Title\tPage Type\tDownload Type\tDevice\tTerritory\tSource Type\tCounts\n'
        report = self.root / 'downloads.tsv'
        report.write_text(cols + '2026-01-01\t123\tShare Save\tProduct page\tFirst-time Download\tiPhone\tUSA\tWeb referrer\t0\n')
        segment = self.ref(report)
        instance = dict(type='downloads', date='2026-01-01', revision=2, segments=[segment, segment])
        manifest = dict(appId='123', granularity='daily', instances=[{**instance, 'revision': 1, 'segments': []}, instance],
                        pageNames=[{'from': '2026-01-01', 'to': '2026-02-01', 'pageId': 'P', 'title': 'Share Save'}])
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        args = ['--input', '.', '--from', '2026-01-01', '--to', '2026-02-01']
        result = self.run_cli('report', *args)
        self.assertEqual(self.run_cli('report', *args), result)
        self.assertEqual(result['rows'][0]['value'], 0)
        self.assertIsNone(result['conversionRate'])
        self.assertEqual(len(result['sourceDigests']), 1)
        manifest['pageNames'].append({**manifest['pageNames'][0], 'pageId': 'P2'})
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.run_cli('report', *args)

    def test_claim_crash_recovery_and_busy_campaign(self):
        plan = self.plan_file()
        operation = self.handoff()['operations'][0]['operationId']
        opts = ['--plan', 'plan.json', '--operation', operation]
        self.assertEqual(self.run_cli('claim', *opts)['status'], 'reserved')
        self.assertEqual(self.run_cli('claim', *opts)['status'], 'blocked')
        self.assertEqual(self.run_cli('reconcile', *opts)['reasonCode'], 'outcomeUnknown')
        self.observation(plan)
        self.proposal['rationale'] = 'Edited during recovery'
        self.save()
        self.assertEqual(self.run_cli('reconcile', *opts)['status'], 'verified')
        self.assertEqual(self.run_cli('reconcile', *opts)['status'], 'verified')

    def test_reviewed_text_can_cycle_without_reusing_an_execution(self):
        ids = []
        current = ''
        for index, desired in enumerate(('A', 'B', 'A')):
            self.loc['promotionalText'] = desired
            self.save()
            plan = self.plan_file()
            self.observation(plan)
            loc = self.snapshot['version']['localizations']['en-US']
            loc['promotionalText'] = current
            self.observe(plan)
            op = next(x for x in self.handoff(f'handoff-{index}.json')['operations'] if x['kind'] == 'updateText')
            args = ('--plan', 'plan.json', '--operation', op['operationId'])
            self.assertEqual(self.run_cli('claim', *args)['status'], 'reserved')
            loc['promotionalText'] = current = desired
            self.observe(plan)
            self.assertEqual(self.run_cli('reconcile', *args)['status'], 'verified')
            ids.append(op['operationId'])
        self.assertEqual(len(set(ids)), 3)

    def test_studio_revision_order_and_preview(self):
        from unittest.mock import Mock
        import io
        import studio_server
        self.stock['assets']['second'] = {**self.stock['assets']['share'], 'artifactId': 'shot2'}
        self.loc['media']['iphone_6_9'].append('second')
        self.proposal['localizations']['en-US'] = {'promotionalText': 'Save text'}
        self.save()
        plan = self.plan_file()
        handler = Mock()
        handler._local_request.return_value = True
        handler.repo_root = self.root
        handler.path = '/api/cpp/share-save/order'
        payload = json.dumps({'locale': 'en-US', 'target': 'iphone_6_9', 'order': ['second', 'share']}).encode()
        handler.headers = {'Content-Type': 'application/json', 'Content-Length': str(len(payload)),
                           'If-Match': '"' + plan['planDigest'] + '"'}
        handler.rfile = io.BytesIO(payload)
        studio_server.StudioRequestHandler.do_POST(handler)
        updated = handler._json.call_args.args[0]
        self.assertEqual(updated['rows'][0]['after'], ['second', 'share'])
        self.assertNotEqual(updated['planDigest'], plan['planDigest'])
        handler.rfile = io.BytesIO(payload)
        studio_server.StudioRequestHandler.do_POST(handler)
        self.assertEqual(handler._json.call_args.args[1], 409)
        handler.path = '/api/cpp/share-save/review'
        studio_server.StudioRequestHandler.do_GET(handler)
        self.assertIn(b'Proposed page', handler._serve_file.call_args.args[2])

    def test_untrusted_page_link_and_unsupported_target(self):
        self.proposal.update(decision='reusePage', pageId='P')
        self.stock['pages'] = [{'pageId': 'P', 'approved': True, 'visible': True,
                                'url': 'https://example.org/id123?ppid=P', 'localizations': {'en-US': self.loc}}]
        self.save()
        self.assertEqual(self.run_cli('plan')['status'], 'blocked')
        self.brief['targets'] = ['mac_16_10']
        self.save()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            self.run_cli('plan')

    def test_media_plan_rejects_wrong_sealed_locale(self):
        plan = self.plan_file()
        self.observation(plan)
        scope = self.handoff()['operations'][-1]['scope']
        asset = dict(role='screenshot', path='media/fr/iphone_6_9/share.png',
                     artifact_id='shot1', sha256=self.ref(self.shot)['sha256'])
        with self.assertRaisesRegex(ValueError, 'locale'):
            publication_assets({'assets': [asset]}, {}, target=scope)

    def test_discover_reads_all_parent_scoped_resources(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        responses = [
            [{'type': 'appCustomProductPages', 'id': 'P', 'relationships': {'app': {'data': {'id': '123'}}}}],
            [{'type': 'appCustomProductPageVersions', 'id': 'V'}],
            [{'type': 'appCustomProductPageLocalizations', 'id': 'L'}]]
        with patch('cpp_discovery.subprocess.run', side_effect=[
                SimpleNamespace(returncode=0, stdout=json.dumps({'data': data})) for data in responses]) as asc:
            args = cli.build_parser().parse_args(['cpp', 'discover', '--app', '123'])
            result = cli.run(args)
            calls = [call.args[0] for call in asc.call_args_list]
        self.assertEqual(result['pages'][0]['versions'][0]['localizations'][0]['id'], 'L')
        self.assertTrue(all('list' in call and '--paginate' in call for call in calls))
        self.assertIn('P', calls[1])
        self.assertIn('V', calls[2])

    def test_discover_rejects_next_cursor_in_aggregated_result(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from cpp_discovery import discover
        response = SimpleNamespace(returncode=0, stdout=json.dumps({'data': [], 'links': {'next': 'cursor'}}))
        with patch('cpp_discovery.subprocess.run', return_value=response), self.assertRaisesRegex(ValueError, 'Incomplete'):
            discover('123')

    def test_pdf_or_corrupt_png_cannot_be_used_as_a_screenshot(self):
        self.shot.write_bytes(b'invalid PNG')
        self.stock['assets']['share'].update(self.ref(self.shot))
        self.save()
        with self.assertRaisesRegex(ValueError, 'PNG'):
            self.run_cli('plan')

    def test_keyword_collision_and_multilocale_gaps(self):
        self.brief['locales'].append('fr-FR')
        self.stock['pages'].append(dict(pageId='P', name='Other', localizations={'en-US': self.loc}))
        self.save()
        blockers = self.run_cli('plan')['blockers']
        self.assertIn('Keyword combination already assigned in en-US', blockers)
        self.assertIn('Provide media for fr-FR/iphone_6_9', blockers)

    def test_refuses_tampered_or_cross_campaign_observation(self):
        self.observation(self.plan_file())
        (self.root / 'asc.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Changed input'):
            self.run_cli('status')
        with self.assertRaisesRegex(ValueError, 'observation is missing'):
            self.run_cli('status', '--observation', 'wrong.json')

    def test_normalization_is_bound_to_set_or_exact_display_type(self):
        plan = self.plan_file()
        self.observation(plan)
        target = self.handoff()['operations'][-1]['scope']
        response = {'customProductPageLocalizationId': 'L', 'sets': [
            {'set': {'id': 'other', 'attributes': {'screenshotDisplayType': 'APP_IPHONE_55'}}},
            {'set': {'id': 'bound', 'attributes': {'screenshotDisplayType': 'APP_IPHONE_69'}}}]}
        plan = {'target': target, 'assets': [{'artifact_id': 'shot1', 'role': 'screenshot'}]}
        scope = {'artifact_id': 'shot1', 'localization_id': 'L'}
        facts = media_response(plan, response, scope)
        self.assertEqual([s['set']['id'] for s in facts['sets']], ['bound'])
        preview = {'target': target, 'assets': [{'artifact_id': 'shot1', 'role': 'preview'}]}
        preview_sets = {'customProductPageLocalizationId': 'L', 'sets': [
            {'set': {'id': 'video', 'attributes': {'previewType': 'IPHONE_67'}}}]}
        self.assertEqual(media_response(preview, preview_sets, scope)['sets'], preview_sets['sets'])
        target['set_ids'] = {'screenshot': 'unknown'}
        with self.assertRaisesRegex(ValueError, 'media set'):
            media_response(plan, response, scope)

    def test_missing_media_returns_reviewable_blocked_plan(self):
        self.loc['media']['iphone_6_9'] = ['missing-scene']
        self.save()
        self.assertEqual(self.plan_file()['status'], 'blocked')
        result = self.run_cli('preview', '--plan', 'plan.json', '--out', 'review')
        self.assertIn('Missing media: missing-scene', Path(result['path']).read_text())

    def test_video_requires_validation_and_poster_readiness(self):
        video = self.root / 'preview.mp4'
        video.write_bytes(b'fixture video bytes')
        asset = {**self.ref(video), 'artifactId': 'preview1', 'role': 'preview',
                 'target': 'iphone_6_9', 'locale': 'en-US'}
        self.stock['assets']['video'] = asset
        self.loc['media']['iphone_6_9'] = ['video']
        self.save()
        self.assertEqual(self.run_cli('plan')['status'], 'blocked')
        evidence = self.root / 'validation.json'
        evidence.write_text(json.dumps({'status': 'PASS', 'assets': {'preview/preview.mp4': {
            'sha256': asset['sha256'], 'type': 'video'}}}))
        asset['validation'] = self.ref(evidence)
        self.save()
        plan = self.plan_file()
        self.observation(plan)
        loc = self.snapshot['version']['localizations']['en-US']
        loc.update(promotionalText='Save text', keywords=['save'], media={'iphone_6_9': [asset['sha256']]},
                   readiness={'iphone_6_9': {asset['sha256']: dict(upload=True, processing=True, media=True)}})
        self.observe(plan)
        self.assertEqual(self.handoff()['pendingMedia'][0]['missing'], ['poster'])

    def test_update_approved_page_prepares_one_new_version(self):
        self.stock['pages'] = [dict(pageId='P', name='Share Save', localizations={'en-US': self.loc})]
        self.proposal.update(decision='updatePage', pageId='P')
        self.save()
        plan = self.plan_file()
        self.observation(plan)
        self.snapshot['version']['state'] = 'APPROVED'
        self.observe(plan)
        self.assertEqual(self.handoff()['reasonCode'], 'refreshAllVersions')
        self.snapshot['versionInventory'] = [dict(pageVersionId='V', state='APPROVED')]
        self.observe(plan)
        self.assertEqual([op['kind'] for op in self.handoff('new.json')['operations']], ['prepareVersion'])
        self.snapshot['versionInventory'].append(dict(pageVersionId='V2', state='IN_REVIEW'))
        self.observe(plan)
        self.assertEqual(self.handoff('locked.json')['operations'], [])

    def test_scoped_handoff_through_managed_seal_approve_and_export(self):
        from artifact_lifecycle import Lifecycle
        config = dict(project=dict(id='demo', name='Demo', bundleId='example.clip', locales=['en-US']),
                      targets=['iphone_6_9'], cards=[dict(id='share', screenshot='share.png')],
                      archivePolicy=dict(schema_version=1, mediaMode='local'),
                      artifactPolicy=dict(schema_version=1, mediaBudgetBytes=1073741824))
        store = Lifecycle(self.root, config)
        run = store.start_run({'version': '1.0', 'platform': 'IOS'})
        attempt = store.start_attempt(run['id'], 'render', 'agent')
        source = store.register(attempt['id'], self.shot, 'source', logical_path='share.png')
        output = store.register(attempt['id'], self.shot, 'screenshot', inputs=[source['id']],
                                logical_path='en-US/iphone_6_9/share.png')
        store.finish_attempt(attempt['id'], 'succeeded')
        candidate = store.select(run['id'], [output['id']])
        validation = store.validate_candidate(candidate['id'])
        self.assertEqual(validation['status'], 'PASS', validation['errors'])
        approval = store.approve_design(candidate['id'], validation['id'], 'owner', 'human:design')
        delivery = store.seal(candidate['id'], validation['id'], approval['id'])
        self.stock['assets']['share']['artifactId'] = output['id']
        self.save()
        self.observation(self.plan_file())
        scope = self.handoff()['operations'][-1]['scope']
        publication = store.plan_publication(delivery['id'], 'local', scope)
        store.approve_upload(publication['id'], 'owner', 'human:upload')
        exported = store.export_publication(publication['id'], write=True)
        self.assertEqual(exported['upload_approval'], 'approved')
        self.assertEqual(publication['target']['page_version_id'], 'V')
        self.assertEqual([a['artifact_id'] for a in publication['assets']], [output['id']])
