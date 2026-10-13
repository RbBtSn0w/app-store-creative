"""Draft storage previews use shared resolution without changing managed state."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import urllib.error
import test_studio_release as fixtures
import export_engine
from artifact_lifecycle import Lifecycle


class StorageConfigurationPreviewTests(unittest.TestCase):
    setUp = fixtures.StudioReleaseTests.setUp
    tearDown = fixtures.StudioReleaseTests.tearDown
    request = fixtures.StudioReleaseTests.request
    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def preview(self, config):
        from storage_configuration import preview
        return preview(self.root, config, self.config, self.cfg)

    def test_default_and_derived_sources_are_reported_without_writes(self):
        before = self.snapshot()
        report = self.preview({**self.config, 'storage': {'workspaceRoot': 'working area'}})
        self.assertEqual(report['binding']['workspace'], str(self.root.resolve() / 'working area'))
        self.assertEqual(report['binding']['objects'], str(self.root.resolve() / 'working area/objects'))
        self.assertEqual(report['roots']['workspaceRoot']['source'], 'project')
        self.assertEqual(report['roots']['objectRoot']['source'], 'derived')
        self.assertEqual(report['roots']['releaseRoot']['source'], 'default')
        self.assertFalse(report['requires_relocation'])
        self.assertTrue(report['roots_changed'])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / 'working area').exists())

    def test_managed_roots_require_migration_but_content_edits_do_not(self):
        Lifecycle(self.root, self.config, self.cfg).start_run({})
        before = self.snapshot()
        self.assertFalse(self.preview({**self.config, 'cards': []})['requires_relocation'])
        report = self.preview({**self.config, 'storage': {'workspaceRoot': 'new work'}})
        self.assertTrue(report['requires_relocation'])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_roots_are_rejected_without_target_creation(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.preview({**self.config, 'storage': {'releaseRoot': '.creative/release'}})
        self.assertEqual(self.snapshot(), before)

    def test_http_and_cli_return_identical_previews_across_restarts(self):
        draft = {**self.config, 'storage': {'workspaceRoot': '素材 work'}}
        draft_path = self.root / 'draft.json'; draft_path.write_text(json.dumps(draft))
        before = self.snapshot()
        expected = self.preview(draft)
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        process = subprocess.run([sys.executable, str(cli), 'storage', 'preview', '--draft',
                                  str(draft_path), '--repo', str(self.root)],
                                 cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), expected)
        for _ in range(2):
            with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
                result, _ = self.request(ctx, '/api/storage/preview', {'config': draft})
                self.assertEqual(result, expected)
        self.assertEqual(self.snapshot(), before)

    def test_http_invalid_draft_reports_error_and_preserves_disk(self):
        before = self.snapshot()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/storage/preview', {'config': {**self.config,
                    'storage': {'publicationRoot': '.creative/publications'}}})
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()
        self.assertEqual(self.snapshot(), before)

    def test_existing_owner_cannot_be_aliased_or_reassigned(self):
        core = Lifecycle(self.root, self.config, self.cfg); core.start_run({})
        owner = core.paths.workspace / 'owner.json'
        bytes_before = owner.read_bytes()
        owner.write_text(json.dumps({'project': str(self.root.resolve()), 'project_id': 'other'}))
        with self.assertRaisesRegex(ValueError, 'another project'):
            self.preview(self.config)
        owner.write_bytes(bytes_before)
        retained = owner.with_name('original-owner.json'); owner.rename(retained)
        owner.symlink_to(retained)
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.preview(self.config)
        self.assertEqual(retained.read_bytes(), bytes_before)

    def test_managed_identity_change_is_reported_separately_from_roots(self):
        Lifecycle(self.root, self.config, self.cfg).start_run({})
        report = self.preview({**self.config, 'project': {**self.config['project'], 'id': 'other'}})
        self.assertTrue(report['project_identity_conflict'])
        self.assertFalse(report['roots_changed'])
        self.assertFalse(report['requires_relocation'])

    def test_cli_and_http_drafts_resolve_protected_local_roots_and_sources(self):
        local = self.cfg.with_name(self.cfg.stem + '.local.json')
        local.write_text(json.dumps({'schema_version': 1, 'project_id': self.config['project']['id'],
                                    'storage': {'workspaceRoot': 'host 素材'}}))
        draft = {**self.config, 'storage': {'workspaceRoot': 'draft shared'}}
        draft_path = self.root / 'draft.json'; draft_path.write_text(json.dumps(draft))
        before = self.snapshot()
        cli = Path(__file__).parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        result = subprocess.run([sys.executable, str(cli), 'storage', 'preview', '--draft',
                                 str(draft_path), '--repo', str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['binding']['workspace'], str(self.root.resolve() / 'host 素材'))
        self.assertEqual(report['roots']['workspaceRoot']['source'], 'local')
        self.assertFalse(report['roots_changed'])
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            actual, _ = self.request(ctx, '/api/storage/preview', {'config': draft})
            self.assertEqual(actual, report)
        self.assertEqual(self.snapshot(), before)
