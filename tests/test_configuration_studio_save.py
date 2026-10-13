"""Studio saves shared drafts against both protected configuration layers."""
import json
import unittest
import urllib.error
import test_studio_release as fixtures
import export_engine
from artifact_lifecycle import Lifecycle


class LayeredStudioSaveTests(unittest.TestCase):
    def setUp(self):
        fixtures.StudioReleaseTests.setUp(self)
        self.root = self.root.resolve(); self.cfg = self.root / self.cfg.name
    tearDown = fixtures.StudioReleaseTests.tearDown
    request = fixtures.StudioReleaseTests.request

    def local(self, workspace='host work'):
        path = self.cfg.with_name('creative.config.local.json')
        path.write_text(json.dumps({'schema_version':1, 'project_id':'demo', 'storage':{'workspaceRoot':workspace}}))
        return path

    def test_save_requires_reviewed_revision_before_any_write(self):
        before = self.cfg.read_bytes()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', {**self.config, 'connectedTrack': True})
            self.assertEqual(failure.exception.code, 428)
            failure.exception.close()
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertFalse((self.root / '.creative').exists())

    def test_local_edit_invalidates_shared_editor_revision(self):
        local = self.local()
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            document, headers = self.request(ctx, '/api/config')
            self.assertNotIn('storage', document)
            before = self.cfg.read_bytes()
            self.local('changed host')
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', self.config, {'If-Match':headers['ETag']})
            self.assertEqual(failure.exception.code, 409); failure.exception.close()
            self.assertEqual(self.cfg.read_bytes(), before)
            self.assertFalse((self.root/'changed host').exists())

    def test_save_uses_effective_roots_and_preserves_local_document(self):
        local = self.local(); original = local.read_bytes()
        core = Lifecycle.from_configuration(self.root, self.cfg); core.start_run({})
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = self.request(ctx, '/api/config')
            draft = {**self.config, 'connectedTrack':True, 'storage':{'workspaceRoot':'shared future'}}
            self.request(ctx, '/api/config', draft, {'If-Match':headers['ETag']})
        self.assertEqual(json.loads(self.cfg.read_text()), draft)
        self.assertEqual(local.read_bytes(), original)
        self.assertFalse((self.root/'shared future').exists())
        self.assertFalse((self.root/'.creative').exists())

    def test_new_local_document_invalidates_revision_and_effective_move_is_refused(self):
        with export_engine.LocalServerContext(self.root, self.cfg) as ctx:
            _, headers = self.request(ctx, '/api/config')
            self.local()
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', self.config, {'If-Match':headers['ETag']})
            self.assertEqual(failure.exception.code, 409); failure.exception.close()
            Lifecycle.from_configuration(self.root, self.cfg).start_run({})
            _, headers = self.request(ctx, '/api/config')
            before = self.cfg.read_bytes()
            draft = {**self.config, 'storage':{'releaseRoot':'moved releases'}}
            with self.assertRaises(urllib.error.HTTPError) as failure:
                self.request(ctx, '/api/config', draft, {'If-Match':headers['ETag']})
            self.assertEqual(failure.exception.code, 400); failure.exception.close()
            self.assertEqual(self.cfg.read_bytes(), before)
            self.assertFalse((self.root/'moved releases').exists())
