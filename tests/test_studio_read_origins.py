"""Studio media stays accessible locally without cross-origin read permission."""
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request
import export_engine


class StudioReadOriginTests(unittest.TestCase):
    def test_foreign_origin_cannot_read_project_media_or_configuration(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            cfg = root / 'creative.config.json'
            cfg.write_text(json.dumps({'project': {'id': 'origin-fixture'}}))
            (root / 'source.png').write_bytes(b'fixture media')
            with export_engine.LocalServerContext(root, cfg) as ctx:
                for path in ('/source.png', '/api/config'):
                    request = urllib.request.Request(f'http://127.0.0.1:{ctx.port}{path}',
                                                     headers={'Origin': 'https://foreign.example'})
                    with self.subTest(path=path):
                        with self.assertRaises(urllib.error.HTTPError) as refused:
                            urllib.request.urlopen(request, timeout=5)
                        self.assertEqual(refused.exception.code, 403)
                        self.assertIsNone(refused.exception.headers.get('Access-Control-Allow-Origin'))

    def test_local_and_same_origin_media_reads_remain_available(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            cfg = root / 'creative.config.json'
            cfg.write_text(json.dumps({'project': {'id': 'origin-fixture'}}))
            content = b'fixture media'; (root / 'source.png').write_bytes(content)
            with export_engine.LocalServerContext(root, cfg) as ctx:
                origin = f'http://127.0.0.1:{ctx.port}'
                for headers in ({}, {'Origin': origin}):
                    with self.subTest(headers=headers):
                        request = urllib.request.Request(origin + '/source.png', headers=headers)
                        with urllib.request.urlopen(request, timeout=5) as response:
                            self.assertEqual(response.read(), content)
                            self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))

    def test_legacy_hidden_asset_route_has_no_special_access(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            cfg = root / 'creative.config.json'
            cfg.write_text(json.dumps({'project': {'id': 'origin-fixture'}}))
            legacy = root / '.creative/assets/old.png'
            legacy.parent.mkdir(parents=True); legacy.write_bytes(b'legacy fixture')
            with export_engine.LocalServerContext(root, cfg) as ctx:
                with self.assertRaises(urllib.error.HTTPError) as refused:
                    urllib.request.urlopen(f'http://127.0.0.1:{ctx.port}/.creative/assets/old.png', timeout=5)
                self.assertEqual(refused.exception.code, 404)
                self.assertEqual(legacy.read_bytes(), b'legacy fixture')
