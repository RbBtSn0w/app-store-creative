#!/usr/bin/env python3
"""Localhost Studio HTTP server for App Store Creative v2.0."""

import json
import base64
import studio_contract as contract
import mimetypes
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional


def is_safe_child(base: Path, candidate: Path) -> bool:
    """Verify that candidate path resolves strictly within base directory (Path Traversal Protection)."""
    try:
        resolved_base = base.resolve()
        resolved_cand = candidate.resolve()
        return resolved_cand == resolved_base or resolved_cand.is_relative_to(resolved_base)
    except Exception:
        return False


class StudioRequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving Studio dist, project config, and captured assets securely."""

    repo_root: Path = Path.cwd()
    studio_dist: Path = Path(__file__).resolve().parent.parent / "studio" / "dist"
    config_path: Path = Path.cwd() / "creative.config.json"

    def log_message(self, format, *args):
        # Suppress routine request logging to keep CLI output clean
        pass

    def _json(self, data, status=200, etag=None):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def _local_request(self):
        try:
            host = urllib.parse.urlsplit('//' + self.headers.get('Host', '')).hostname
        except ValueError:
            host = None
        if host not in ('localhost', '127.0.0.1', '::1'):
            self._json({'ok': False, 'error': 'Open Studio using a loopback address'}, 403)
            return False
        return True

    def do_OPTIONS(self):
        self._json({"ok": False, "error": "Cross-origin requests are not supported"}, 403)

    def do_GET(self):
        if not self._local_request():
            return
        path = urllib.parse.unquote(self.path.split("?")[0])
        if path == "/api/config":
            try:
                with contract.WRITE_LOCK:
                    data = self.config_bytes if getattr(self, 'config_bytes', None) is not None else (
                        self.config_path.read_bytes() if self.config_path.exists() else b'{}')
                    config = json.loads(data)
                    if config != {}:
                        contract.check_config(config)
                        # Materialize existing visual defaults for legacy manifests in the editor.
                        config.setdefault('theme', {}).setdefault('background', {'type': 'gradient', 'colors': ['#0A0E1A', '#311042']})
                        config.setdefault('targets', ['iphone_6_9'])
                        config['project'].setdefault('locales', ['en-US'])
                        for card in config['cards']:
                            card.setdefault('headline', card['id'])
                    self._json(config, etag='"' + (contract.digest(data) if getattr(self, 'config_bytes', None) is not None or self.config_path.exists() else 'missing') + '"')
            except (ValueError, TypeError) as error:
                self._json({'ok': False, 'error': f'Project needs repair: {error}'}, 400)
            except OSError as error:
                self._json({'ok': False, 'error': f'Could not read project: {error}'}, 500)
            return
        if path == "/api/health":
            import export_engine
            self._json({"status": "ok", "version": "2.0.0", "chrome": bool(export_engine.find_chrome_binary())})
            return
        if path == "/api/status":
            if self.job.get('running'):
                self._json(dict(self.job))
                return
            try:
                import production_lifecycle
                with contract.WRITE_LOCK:
                    reviewed_revision = contract.revision(self.config_path)
                    config = contract.check_config(json.loads(self.config_path.read_bytes()))
                    _, input_errors = contract.input_hashes(self.repo_root, config)
                    import export_engine
                    if not export_engine.find_chrome_binary():
                        input_errors.append('Install Chrome or Chromium before exporting')
                    current = production_lifecycle.latest(self.repo_root, self.config_path)
                    if reviewed_revision != contract.revision(self.config_path):
                        raise ValueError('Inputs changed while checking; review and check again')
                self._json({**self.job, **current, "running": False, "configRevision": reviewed_revision, "inputErrors": input_errors})
            except Exception as error:
                self._json({**self.job, 'running': False, 'validation': None, 'error': str(error)})
            return
        if path.startswith('/api/artifacts/'):
            try:
                from artifact_lifecycle import Lifecycle
                parts = path.split('/', 4)
                if len(parts) != 5:
                    raise ValueError('Missing artifact identity')
                core = Lifecycle(self.repo_root, json.loads(self.config_path.read_text()), self.config_path)
                candidate = core._read('candidates', parts[3])
                for identity in candidate['artifacts']:
                    artifact = core.verify_artifact(identity)
                    if artifact.get('logical_path') == parts[4] and artifact['role'] in ('screenshot', 'poster', 'preview'):
                        self._serve_file(core.object_path(artifact['sha256']), 'video/mp4' if artifact['role'] == 'preview' else 'image/png')
                        return
                raise ValueError('Artifact is not part of candidate')
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 404)
            return
        rel = path.lstrip('/')
        candidate = self.repo_root / rel
        snapshot = getattr(self, 'asset_bytes', {}).get(rel)
        if snapshot is not None and is_safe_child(self.repo_root, candidate):
            self._serve_file(candidate, content=snapshot)
            return
        if rel.startswith('api/inputs/'):
            try:
                from artifact_lifecycle import Lifecycle
                core = Lifecycle(self.repo_root, json.loads(self.config_path.read_text()), self.config_path)
                imported, source = core.resolve_import(rel)
                self._serve_file(source, 'image/png' if rel.endswith('.png') else 'image/jpeg')
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 404)
            return
        # Serve only image assets from the consuming project, never its secrets or source.
        if rel and is_safe_child(self.repo_root, candidate) and candidate.is_file() and candidate.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            if not any(part.startswith('.') for part in Path(rel).parts) or rel.startswith('.creative/assets/'):
                self._serve_file(candidate)
                return
        dist = self.studio_dist / rel
        if rel and is_safe_child(self.studio_dist, dist) and dist.is_file():
            self._serve_file(dist)
            return
        if Path(rel).suffix:
            self.send_error(404, "Asset not found")
            return
        index = self.studio_dist / 'index.html'
        if index.exists():
            self._serve_file(index, 'text/html')
        else:
            self.send_error(404, "Studio bundle not found")

    def do_POST(self):
        if not self._local_request():
            return
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if origin and origin != f'http://{host}':
            self._json({"ok": False, "error": "Cross-origin writes are not allowed"}, 403)
            return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self._json({"ok": False, "error": "Use application/json"}, 415)
            return
        path = urllib.parse.unquote(self.path.split('?')[0])
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 30 * 1024 * 1024 or self.headers.get('Transfer-Encoding'):
                self._json({"ok": False, "error": "Request size must be between 1 byte and 30 MB"}, 413)
                return
            self.connection.settimeout(20)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Request must be a JSON object')
            if path == '/api/config':
                contract.check_config(payload)
                with contract.WRITE_LOCK:
                    expected = self.headers.get('If-Match')
                    if expected and expected != contract.revision(self.config_path):
                        self._json({"ok": False, "error": "Project changed in another tab or agent. Reload or keep your draft."}, 409)
                        return
                    from artifact_lifecycle import Lifecycle
                    core = Lifecycle(self.repo_root, payload, self.config_path)
                    if self.config_path.exists():
                        previous = json.loads(self.config_path.read_text())
                        previous_core = Lifecycle(self.repo_root, previous, self.config_path)
                        owned = (previous_core.paths.workspace / 'owner.json').exists()
                        if owned and previous_core.paths.binding() != core.paths.binding():
                            raise ValueError('Existing storage requires explicit relocate before changing roots')
                        if owned and previous.get('project', {}).get('id') != payload.get('project', {}).get('id'):
                            raise ValueError('Managed project identity cannot change during configuration save')
                        (previous_core if owned else core).backup_configuration(self.config_path.read_bytes(), 'studio-user')
                    contract.atomic_json(self.config_path, payload)
                    self._json({"ok": True}, etag=contract.revision(self.config_path))
                return
            if path == '/api/assets':
                data = base64.b64decode(payload.get('data', ''), validate=True)
                from artifact_lifecycle import Lifecycle
                with contract.WRITE_LOCK:
                    core = Lifecycle(self.repo_root, json.loads(self.config_path.read_text()), self.config_path)
                    imported = core.import_capture(data, str(payload.get('name', 'Capture')), 'studio-user')
                self._json({'ok': True, **imported})
                return
            if path == '/api/export':
                import export_engine
                import validator
                with contract.WRITE_LOCK:
                    if self.job.get('running'):
                        self._json({"ok": False, "error": "An export is already running"}, 409)
                        return
                    if self.headers.get('If-Match') != contract.revision(self.config_path):
                        self._json({"ok": False, "error": "Save the current project before exporting"}, 409)
                        return
                    self.job.clear()
                    self.job.update(running=True, completed=0, total=0)
                try:
                    def progress(completed, total, item):
                        self.job.update(completed=completed, total=total, item=item)
                    import production_lifecycle
                    result = production_lifecycle.produce(self.repo_root, self.config_path,
                        targets=[payload['target']] if payload.get('scope') == 'selected' else None,
                        locales=[payload['locale']] if payload.get('scope') == 'selected' else None,
                        progress=progress, expected_revision=self.headers.get('If-Match'))
                    validation = result['validation']
                    self.job.update(running=False, completed=result['export']['total_rendered'], validation=validation,
                                    candidate_id=result['candidate_id'], run_id=result['run_id'])
                    self._json({"ok": result.get('status') == 'PASS', "scope": payload.get('scope', 'all'),
                                "result": result, "validation": validation})
                finally:
                    self.job['running'] = False
                return
            self._json({"ok": False, "error": "Unknown endpoint"}, 404)
        except (ValueError, KeyError, TypeError) as error:
            self._json({"ok": False, "error": str(error)}, 400)
        except Exception as error:
            self._json({"ok": False, "error": str(error)}, 500)

    def _serve_file(self, file_path: Path, content_type: Optional[str] = None, content=None):
        if not content_type:
            suffix = file_path.suffix.lower()
            if suffix in (".js", ".mjs"):
                content_type = "application/javascript"
            elif suffix == ".css":
                content_type = "text/css"
            elif suffix == ".svg":
                content_type = "image/svg+xml"
            elif suffix == ".json":
                content_type = "application/json"
            elif suffix in (".png", ".jpg", ".jpeg"):
                content_type = f"image/{'jpeg' if suffix in ('.jpg', '.jpeg') else 'png'}"
            else:
                content_type, _ = mimetypes.guess_type(str(file_path))
        content_type = content_type or "application/octet-stream"

        try:
            if content is None:
                content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")


def make_handler(root, config, config_bytes=None, asset_bytes=None):
    """Bind immutable server identity without mutating a global handler class."""
    return type('ProjectStudioHandler', (StudioRequestHandler,), {
        'repo_root': root.resolve(), 'config_path': config.resolve(),
        'config_bytes': config_bytes, 'asset_bytes': asset_bytes or {}, 'job': {'running': False},
    })


def run_studio_server(port: int = 3100, repo_root: Optional[Path] = None, config_path: Optional[Path] = None):
    """Run Studio HTTP server synchronously with SO_REUSEADDR enabled."""
    repo = repo_root or Path.cwd()
    cfg = config_path or (repo / "creative.config.json")
    handler = make_handler(repo, cfg)

    ThreadingHTTPServer.allow_reuse_address = True
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, handler)
    print(f"🚀 App Store Creative Studio running at: http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Studio server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_studio_server()
