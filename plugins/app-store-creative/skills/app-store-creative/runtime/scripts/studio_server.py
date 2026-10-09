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
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host", "")}':
            self._json({'ok': False, 'error': 'Cross-origin requests are not allowed'}, 403)
            return False
        return True

    def do_OPTIONS(self):
        self._json({"ok": False, "error": "Cross-origin requests are not supported"}, 403)

    def do_GET(self):
        if not self._local_request():
            return
        path = urllib.parse.unquote(self.path.split("?")[0])
        if path == '/api/storage/media-budget':
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
                if set(query) - {'candidate_id'} or ('candidate_id' in query and len(query['candidate_id']) != 1):
                    raise ValueError('Media budget accepts one optional candidate_id')
                candidate = safe_id(query['candidate_id'][0]) if 'candidate_id' in query else None
                with contract.WRITE_LOCK:
                    self._json(Lifecycle.from_configuration(self.repo_root, self.config_path).media_budget(candidate))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/storage/artifact-policy':
            try:
                from artifact_lifecycle import Lifecycle
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Artifact policy inspection does not accept overrides')
                with contract.WRITE_LOCK:
                    self._json(Lifecycle.from_configuration(self.repo_root, self.config_path).inspect_artifact_policy())
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path in ('/api/storage/relocation-status', '/api/storage/relocated-objects'):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
                if set(query) != {'id'} or len(query['id']) != 1:
                    raise ValueError('Relocation status requires exactly one id')
                from artifact_lifecycle import Lifecycle, safe_id
                safe_id(query['id'][0])
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    result = (core.relocated_object_status(query['id'][0]) if path == '/api/storage/relocated-objects' else core.relocation_status(query['id'][0]))
                self._json(result)
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/relocation-maintenance':
            try:
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Relocation maintenance observations do not accept overrides')
                from artifact_lifecycle import Lifecycle
                with contract.WRITE_LOCK:
                    result = Lifecycle.from_configuration(self.repo_root, self.config_path).inventory()['quarantine_preparations']
                self._json(result)
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/maintenance':
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
                if set(query) - {'limit', 'cursor'} or any(len(values) != 1 for values in query.values()):
                    raise ValueError('Maintenance reads only accept limit and cursor')
                limit = int(query.get('limit', ['20'])[0])
                cursor = query.get('cursor', [None])[0]
                from artifact_lifecycle import Lifecycle
                with contract.WRITE_LOCK:
                    result = Lifecycle.from_configuration(self.repo_root, self.config_path).list_maintenance(limit, cursor)
                self._json(result)
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == "/api/config":
            try:
                with contract.WRITE_LOCK:
                    data = self.config_bytes if getattr(self, 'config_bytes', None) is not None else (
                        self.config_path.read_bytes() if self.config_path.exists() else b'{}')
                    config = json.loads(data)
                    editor_revision = '"' + (contract.digest(data) if getattr(self, 'config_bytes', None) is not None or self.config_path.exists() else 'missing') + '"'
                    if getattr(self, 'config_bytes', None) is None and self.config_path.exists():
                        from configuration_layers import load
                        layers = load(self.repo_root, self.config_path)
                        config = layers.project_config
                        editor_revision = '"' + layers.revision + '"'
                    if config != {}:
                        contract.check_config(config)
                        # Materialize optional visual defaults for the shared recipe editor.
                        config.setdefault('theme', {}).setdefault('background', {'type': 'gradient', 'colors': ['#0A0E1A', '#311042']})
                        config.setdefault('targets', ['iphone_6_9'])
                        config['project'].setdefault('locales', ['en-US'])
                        for card in config['cards']:
                            card.setdefault('headline', card['id'])
                    self._json(config, etag=editor_revision)
            except (ValueError, TypeError) as error:
                self._json({'ok': False, 'error': f'Project needs repair: {error}'}, 400)
            except OSError as error:
                self._json({'ok': False, 'error': f'Could not read project: {error}'}, 500)
            return
        if path == "/api/health":
            import export_engine
            self._json({"status": "ok", "version": "2.0.0", "chrome": bool(export_engine.find_chrome_binary())})
            return
        if path.startswith('/api/history/maintenance/'):
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Maintenance inspection does not accept query overrides')
                identity = safe_id(path.removeprefix('/api/history/maintenance/'))
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    self._json(core.maintenance_status(identity))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/history/operations':
            try:
                from artifact_lifecycle import Lifecycle
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Operation journals do not accept query overrides')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    self._json(core.operation_journals())
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/history':
            try:
                from artifact_lifecycle import Lifecycle
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('History uses project configuration and accepts no query parameters')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    self._json(core.verify_history())
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/inventory':
            try:
                from artifact_lifecycle import Lifecycle
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Inventory uses project configuration and accepts no query parameters')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    self._json(core.inventory())
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == "/api/status":
            if self.job.get('running'):
                self._json({**self.job, 'production_job': dict(self.job)})
                return
            try:
                import production_lifecycle
                with contract.WRITE_LOCK:
                    from configuration_layers import load
                    layers = load(self.repo_root, self.config_path)
                    reviewed_revision = '"' + layers.revision + '"'
                    config = contract.check_config(layers.config)
                    _, input_errors = contract.input_hashes(self.repo_root, config)
                    import export_engine
                    if not export_engine.find_chrome_binary():
                        input_errors.append('Install Chrome or Chromium before exporting')
                    current = production_lifecycle.latest(self.repo_root, self.config_path)
                    if load(self.repo_root, self.config_path) != layers:
                        raise ValueError('Inputs changed while checking; review and check again')
                self._json({**self.job, **current, "production_job": dict(self.job), "running": False, "configRevision": reviewed_revision, "inputErrors": input_errors})
            except Exception as error:
                self._json({**self.job, 'production_job': dict(self.job), 'running': False, 'validation': None, 'error': str(error)})
            return
        if path == '/api/runs':
            try:
                from artifact_lifecycle import Lifecycle
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if any(key not in ('limit', 'cursor') or len(values) != 1 for key, values in query.items()):
                    raise ValueError('Run list accepts one limit and one cursor')
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                self._json(core.list_runs(int(query.get('limit', ['20'])[0]), query.get('cursor', [None])[0]))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path.startswith('/api/runs/'):
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                identity = safe_id(path.removeprefix('/api/runs/'))
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                self._json(core.status(identity))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 404)
            return
        if path.startswith('/api/candidates/') and path.endswith('/review'):
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Candidate review does not accept query overrides')
                identity = safe_id(path.removeprefix('/api/candidates/').removesuffix('/review'))
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    self._json(core.candidate_review(identity))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path.startswith('/api/publication-handoff/'):
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Handoff preview does not accept query overrides')
                identity = safe_id(path.removeprefix('/api/publication-handoff/'))
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    self._json(core.export_publication(identity, write=False))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/publications':
            try:
                from artifact_lifecycle import Lifecycle
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
                if any(key not in ('limit', 'cursor') or len(values) != 1 for key, values in query.items()):
                    raise ValueError('Publication list accepts one limit and one cursor')
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                self._json(core.list_publications(int(query.get('limit', ['20'])[0]), query.get('cursor', [None])[0]))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path.startswith('/api/publications/'):
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Publication status does not accept query overrides')
                identity = safe_id(path.removeprefix('/api/publications/'))
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                self._json(core.publication_status(identity))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path == '/api/deliveries':
            try:
                from artifact_lifecycle import Lifecycle
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if any(key not in ('limit', 'cursor') or len(values) != 1 for key, values in query.items()):
                    raise ValueError('Delivery list accepts one limit and one cursor')
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                self._json(core.list_deliveries(int(query.get('limit', ['20'])[0]), query.get('cursor', [None])[0]))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 400)
            return
        if path.startswith('/api/deliveries/'):
            try:
                from artifact_lifecycle import Lifecycle, safe_id
                identity = safe_id(path.removeprefix('/api/deliveries/'))
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                self._json(core.delivery_status(identity))
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 404)
            return
        if path.startswith('/api/artifacts/'):
            try:
                from artifact_lifecycle import Lifecycle
                parts = path.split('/', 4)
                if len(parts) != 5:
                    raise ValueError('Missing artifact identity')
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
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
                core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                imported, source = core.resolve_import(rel)
                self._serve_file(source, 'image/png' if rel.endswith('.png') else 'image/jpeg')
            except (ValueError, OSError) as error:
                self._json({'error': str(error)}, 404)
            return
        # Serve only image assets from the consuming project, never its secrets or source.
        if rel and is_safe_child(self.repo_root, candidate) and candidate.is_file() and candidate.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            if not any(part.startswith('.') for part in Path(rel).parts):
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
            if path == '/api/publications/persist-evidence':
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query or set(payload) != {'evidence_id', 'backend', 'confirm'}:
                    raise ValueError('Evidence persistence requires exact fields and no path overrides')
                safe_id(payload['evidence_id'])
                if payload['confirm'] != 'PERSIST' or not isinstance(payload['backend'], str):
                    raise ValueError('Explicit evidence persistence confirmation is required')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    result = core.persist_observation_evidence(payload['evidence_id'], payload['backend'])
                self._json(result)
                return
            if path == '/api/publications/retain-evidence':
                from artifact_lifecycle import Lifecycle, safe_id
                required = {'observation_id', 'actor', 'confirm', 'evidence_base64'}
                if urllib.parse.urlsplit(self.path).query or set(payload) != required:
                    raise ValueError('Evidence retention requires exact fields and no query overrides')
                safe_id(payload['observation_id'])
                if payload['confirm'] != 'RETAIN' or not isinstance(payload['evidence_base64'], str):
                    raise ValueError('Explicit evidence retention confirmation is required')
                try:
                    evidence = base64.b64decode(payload['evidence_base64'], validate=True)
                except ValueError as error:
                    raise ValueError('Invalid encoded observation evidence') from error
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    result = core.retain_observation_evidence(payload['observation_id'], evidence, payload['actor'])
                self._json(result)
                return
            if path in ('/api/publications/approve-upload', '/api/publications/export'):
                from artifact_lifecycle import Lifecycle, safe_id
                approve = path.endswith('/approve-upload')
                required = {'publication_id', 'confirm'} | ({'actor', 'authorization_reference'} if approve else set())
                if urllib.parse.urlsplit(self.path).query or set(payload) != required:
                    raise ValueError('Publication action requires exact fields and no query overrides')
                safe_id(payload['publication_id'])
                if payload['confirm'] != ('UPLOAD' if approve else 'EXPORT'):
                    raise ValueError('Explicit publication confirmation is required')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    result = (core.approve_upload(payload['publication_id'], payload['actor'], payload['authorization_reference'])
                              if approve else core.export_publication(payload['publication_id'], write=True))
                self._json(result)
                return
            if path in ('/api/storage/resume-relocate', '/api/storage/rollback-relocate',
                        '/api/storage/resume-reverse-relocate', '/api/storage/rollback-reverse-relocate'):
                from artifact_lifecycle import safe_id
                from relocation_lifecycle import recovery_source
                if urllib.parse.urlsplit(self.path).query or set(payload) != {'id', 'actor', 'reason', 'confirm', 'source_workspace'}:
                    raise ValueError('Recovery requires exact fields and no query overrides')
                safe_id(payload['id'])
                action = path.rsplit('/', 1)[-1]
                if payload['confirm'] != ('RESUME' if action.startswith('resume') else 'ROLLBACK'):
                    raise ValueError('Explicit recovery confirmation is required')
                if any(not isinstance(payload[key], str) or not payload[key].strip() for key in ('actor', 'reason', 'source_workspace')):
                    raise ValueError('Recovery requires operator, reason and original workspace')
                workspace = Path(payload['source_workspace'])
                if not workspace.is_absolute():
                    workspace = self.repo_root / workspace
                with contract.WRITE_LOCK:
                    core = recovery_source(self.repo_root, self.config_path, workspace, payload['id'])
                    methods = {'resume-relocate': core.resume_relocation,
                               'rollback-relocate': core.rollback_relocation,
                               'resume-reverse-relocate': core.resume_reverse_relocation,
                               'rollback-reverse-relocate': core.rollback_reverse_relocation}
                    result = methods[action](payload['id'], payload['actor'], payload['reason'])
                self._json(result)
                return
            if path in ('/api/storage/plan-relocate', '/api/storage/verify-relocate',
                        '/api/storage/prepare-relocate', '/api/storage/switch-relocate',
                        '/api/storage/plan-reverse-relocate', '/api/storage/verify-reverse-relocate',
                        '/api/storage/prepare-reverse-relocate', '/api/storage/switch-reverse-relocate'):
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Relocation actions do not accept query overrides')
                action = path.rsplit('/', 1)[-1]
                required = {'storage'} if action == 'plan-relocate' else (
                    {'id'} if action in ('verify-relocate', 'plan-reverse-relocate', 'verify-reverse-relocate') else {'id', 'actor', 'reason', 'confirm'})
                if set(payload) != required:
                    raise ValueError('Relocation action requires exact fields')
                if action != 'plan-relocate':
                    safe_id(payload['id'])
                if action.startswith(('prepare-', 'switch-')):
                    if payload['confirm'] != ('PREPARE' if action.startswith('prepare-') else 'SWITCH'):
                        raise ValueError('Explicit relocation confirmation is required')
                    if any(not isinstance(payload[key], str) or not payload[key].strip() for key in ('actor', 'reason')):
                        raise ValueError('Relocation requires actor and reason')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    if action == 'plan-reverse-relocate':
                        result = core.plan_reverse_relocation(payload['id'])
                    elif action == 'verify-reverse-relocate':
                        result = core.verify_reverse_relocation_plan(payload['id'])
                    elif action == 'prepare-reverse-relocate':
                        result = core.prepare_reverse_relocation(payload['id'], payload['actor'], payload['reason'])
                    elif action == 'switch-reverse-relocate':
                        result = core.switch_reverse_relocation(payload['id'], payload['actor'], payload['reason'])
                    elif action == 'plan-relocate':
                        result = core.plan_relocation(payload['storage'])
                    elif action == 'verify-relocate':
                        result = core.verify_relocation_plan(payload['id'])
                    elif action == 'prepare-relocate':
                        result = core.prepare_relocation(payload['id'], payload['actor'], payload['reason'])
                    else:
                        result = core.switch_relocation(payload['id'], payload['actor'], payload['reason'])
                self._json(result)
                return
            relocation_maintenance = {
                'verify': 'verify_relocation_retention',
                'prepare': 'prepare_relocation_quarantine',
                'resume': 'resume_relocation_quarantine_preparation',
                'cancel': 'cancel_relocation_quarantine_preparation',
                'commit': 'commit_relocation_quarantine',
                'restore': 'restore_relocation_quarantine',
                'verify-purge': 'verify_relocation_purge',
                'purge': 'purge_relocation',
            }
            if path.startswith('/api/relocation-maintenance/'):
                from artifact_lifecycle import Lifecycle, safe_id
                action = path.rsplit('/', 1)[-1]
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Relocation maintenance does not accept query overrides')
                if action not in relocation_maintenance and action not in ('plan', 'plan-purge'):
                    raise ValueError('Unknown relocation maintenance action')
                readonly = action in ('verify', 'verify-purge')
                fields = {'retention_days'} if action == 'plan' else (
                    {'id', 'quarantine_days'} if action == 'plan-purge' else (
                        {'id'} if readonly else {'id', 'actor', 'reason', 'confirm'}))
                if set(payload) != fields:
                    raise ValueError('Relocation maintenance requires exact fields')
                if 'id' in fields:
                    safe_id(payload['id'])
                if action in ('plan', 'plan-purge'):
                    days = payload['retention_days' if action == 'plan' else 'quarantine_days']
                    if type(days) is not int or days < 0:
                        raise ValueError('Retention days must be a nonnegative integer')
                elif not readonly:
                    if payload['confirm'] != action.upper():
                        raise ValueError('Explicit relocation maintenance confirmation is required')
                    if any(not isinstance(payload[key], str) or not payload[key].strip() for key in ('actor', 'reason')):
                        raise ValueError('Relocation maintenance requires actor and reason')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    if action == 'plan':
                        result = core.plan_relocation_retention(retention_days=days)
                    elif action == 'plan-purge':
                        result = core.plan_relocation_purge(payload['id'], days)
                    elif readonly:
                        result = getattr(core, relocation_maintenance[action])(payload['id'])
                    else:
                        result = getattr(core, relocation_maintenance[action])(
                            payload['id'], payload['actor'], payload['reason'])
                self._json(result)
                return
            if path in ('/api/maintenance/plan', '/api/maintenance/quarantine', '/api/maintenance/restore',
                        '/api/maintenance/plan-purge', '/api/maintenance/purge'):
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Maintenance actions do not accept query overrides')
                action = path.rsplit('/', 1)[-1]
                required = {'retention_days'} if action == 'plan' else (
                    {'id', 'quarantine_days'} if action == 'plan-purge' else {'id', 'actor', 'reason', 'confirm'})
                if set(payload) != required:
                    raise ValueError('Maintenance action requires exact fields')
                if action in ('plan', 'plan-purge'):
                    days = payload['retention_days' if action == 'plan' else 'quarantine_days']
                    if type(days) is not int or days < 0:
                        raise ValueError('Retention days must be a nonnegative integer')
                    if action == 'plan-purge':
                        safe_id(payload['id'])
                else:
                    safe_id(payload['id'])
                    if payload['confirm'] != action.upper():
                        raise ValueError('Explicit maintenance confirmation is required')
                    if any(not isinstance(payload[key], str) or not payload[key].strip() for key in ('actor', 'reason')):
                        raise ValueError('Maintenance requires actor and reason')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    if action == 'plan':
                        result = core.plan_cleanup(days)
                    elif action == 'plan-purge':
                        result = core.plan_purge(payload['id'], days)
                    elif action == 'quarantine':
                        result = core.quarantine_cleanup(payload['id'], payload['actor'], payload['reason'])
                    elif action == 'purge':
                        result = core.purge_cleanup(payload['id'], payload['actor'], payload['reason'])
                    else:
                        result = core.restore_cleanup(payload['id'], payload['actor'], payload['reason'])
                self._json(result)
                return
            if path in ('/api/candidates/validate', '/api/approvals/design', '/api/deliveries/seal'):
                from artifact_lifecycle import Lifecycle, safe_id
                if urllib.parse.urlsplit(self.path).query:
                    raise ValueError('Lifecycle actions do not accept query overrides')
                required = {'candidate_id'}
                if path == '/api/approvals/design':
                    required |= {'validation_id', 'actor', 'authorization_reference', 'confirm'}
                elif path == '/api/deliveries/seal':
                    required |= {'validation_id', 'approval_id', 'confirm'}
                if set(payload) != required:
                    raise ValueError('Lifecycle action requires exactly its declared fields')
                for key in required & {'candidate_id', 'validation_id', 'approval_id'}:
                    safe_id(payload[key])
                if path == '/api/approvals/design':
                    if payload['confirm'] != 'APPROVE':
                        raise ValueError('Explicit design approval confirmation is required')
                    for key in ('actor', 'authorization_reference'):
                        if not isinstance(payload[key], str) or not payload[key].strip():
                            raise ValueError('Approval requires an actor and authorization reference')
                if path == '/api/deliveries/seal' and payload['confirm'] != 'SEAL':
                    raise ValueError('Explicit archive sealing confirmation is required')
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    if path == '/api/candidates/validate':
                        result = core.validate_candidate(payload['candidate_id'])
                    elif path == '/api/approvals/design':
                        result = core.approve_design(payload['candidate_id'], payload['validation_id'],
                                                     payload['actor'], payload['authorization_reference'])
                    else:
                        result = core.seal(payload['candidate_id'], payload['validation_id'], payload['approval_id'])
                    self._json(result)
                return
            if path == '/api/storage/preview':
                from storage_configuration import preview
                if set(payload) != {'config'}:
                    raise ValueError('Storage preview requires only a config draft')
                with contract.WRITE_LOCK:
                    if self.config_path.exists():
                        from storage_configuration import preview_configuration
                        report = preview_configuration(self.repo_root, payload['config'], self.config_path)
                    else:
                        report = preview(self.repo_root, payload['config'], None, self.config_path)
                    self._json(report)
                return
            if path == '/api/config':
                contract.check_config(payload)
                with contract.WRITE_LOCK:
                    from configuration_layers import load, compose
                    layers = load(self.repo_root, self.config_path) if self.config_path.exists() else None
                    current_revision = '"' + layers.revision + '"' if layers else '"missing"'
                    expected = self.headers.get('If-Match')
                    if expected and expected != current_revision:
                        self._json({"ok": False, "error": "Project or host-local configuration changed. Reload or keep your draft."}, 409)
                        return
                    from artifact_lifecycle import Lifecycle
                    _, paths, _ = compose(self.repo_root, payload, layers.local_config if layers else None)
                    if layers:
                        previous_core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                        owned = (previous_core.paths.workspace / 'owner.json').exists()
                        if owned and previous_core.paths.binding() != paths.binding():
                            raise ValueError('Existing storage requires explicit relocate before changing roots')
                        if owned and layers.project_config.get('project', {}).get('id') != payload.get('project', {}).get('id'):
                            raise ValueError('Managed project identity cannot change during configuration save')
                        previous_core.backup_configuration(layers.project_bytes, 'studio-user')
                        if load(self.repo_root, self.config_path) != layers:
                            raise ValueError('Configuration layers changed before save')
                    contract.atomic_json(self.config_path, payload)
                    updated = load(self.repo_root, self.config_path)
                    self._json({"ok": True}, etag='"' + updated.revision + '"')
                return
            if path == '/api/assets':
                data = base64.b64decode(payload.get('data', ''), validate=True)
                from artifact_lifecycle import Lifecycle
                with contract.WRITE_LOCK:
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    imported = core.import_capture(data, str(payload.get('name', 'Capture')), 'studio-user')
                self._json({'ok': True, **imported})
                return
            if path == '/api/preview/poster':
                from artifact_lifecycle import Lifecycle
                from managed_poster import produce
                with contract.WRITE_LOCK:
                    if self.job.get('running'):
                        self._json({'ok': False, 'error': 'A production job is already running'}, 409)
                        return
                    core = Lifecycle.from_configuration(self.repo_root, self.config_path)
                    if self.headers.get('If-Match') != '"' + core._configuration_layers.revision + '"':
                        self._json({'ok': False, 'error': 'Save the current project before extracting a poster'}, 409)
                        return
                    run = core._run(payload['run_id'])
                    from artifact_lifecycle import configuration_identity
                    if run['config_sha256'] != configuration_identity(core.config):
                        raise ValueError('Poster run configuration is stale')
                    self.job.clear()
                    self.job.update(running=True, stage='poster', run_id=run['id'])
                try:
                    result = produce(core, payload['run_id'], payload['preview_id'], payload['timestamp'], 'studio', retry_of=payload.get('retry_of'))
                    self.job.update(result=result, poster_artifact_id=result['poster_artifact_id'])
                    self._json({'ok': True, 'result': result})
                except Exception as error:
                    self.job.update(error=str(error))
                    raise
                finally:
                    self.job['running'] = False
                return
            if path == '/api/export':
                import export_engine
                import validator
                with contract.WRITE_LOCK:
                    if self.job.get('running'):
                        self._json({"ok": False, "error": "An export is already running"}, 409)
                        return
                    from configuration_layers import load
                    if self.headers.get('If-Match') != '"' + load(self.repo_root, self.config_path).revision + '"':
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
