#!/usr/bin/env python3
"""Localhost Studio HTTP server for App Store Creative v2.0."""

import json
import mimetypes
import os
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

    def do_OPTIONS(self):
        """Handle CORS pre-flight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        raw_path = self.path.split("?")[0]
        unquoted = urllib.parse.unquote(raw_path)

        # 1. API: Get current creative.config.json
        if unquoted == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.config_path.exists():
                self.wfile.write(self.config_path.read_bytes())
            else:
                self.wfile.write(b"{}")
            return

        # 2. API: Health Check
        if unquoted == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "version": "2.0.0"}).encode())
            return

        clean_rel = unquoted.lstrip("/")

        # 3. Serve local project screenshots / assets securely
        if clean_rel:
            repo_candidate = self.repo_root / clean_rel
            if is_safe_child(self.repo_root, repo_candidate) and repo_candidate.is_file():
                self._serve_file(repo_candidate)
                return

        # 4. Serve Studio frontend assets from dist/ securely
        if clean_rel:
            dist_candidate = self.studio_dist / clean_rel
            if is_safe_child(self.studio_dist, dist_candidate) and dist_candidate.is_file():
                self._serve_file(dist_candidate)
                return

        # 5. SPA Fallback: serve dist/index.html
        index_file = self.studio_dist / "index.html"
        if index_file.exists():
            self._serve_file(index_file, "text/html")
            return

        self.send_error(404, "File Not Found")

    def do_POST(self):
        raw_path = self.path.split("?")[0]
        unquoted = urllib.parse.unquote(raw_path)

        # Handle UI-triggered Export
        if unquoted == "/api/export":
            content_len = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_len) if content_len > 0 else b"{}"
            try:
                payload = json.loads(body_bytes.decode() or "{}")
                # Import export_engine dynamically
                import export_engine
                targets = [payload["target"]] if "target" in payload else None
                locales = [payload["locale"]] if "locale" in payload else None

                res = export_engine.run_export(
                    repo_root=self.repo_root,
                    config_path=self.config_path,
                    targets=targets,
                    locales=locales,
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "ok": True,
                    "message": f"Successfully exported {res.get('total_rendered', 0)} assets to artifacts/",
                    "total_rendered": res.get("total_rendered", 0)
                }).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
            return

        self.send_error(404, "Not Found")

    def _serve_file(self, file_path: Path, content_type: Optional[str] = None):
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
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")


def run_studio_server(port: int = 3100, repo_root: Optional[Path] = None, config_path: Optional[Path] = None):
    """Run Studio HTTP server synchronously with SO_REUSEADDR enabled."""
    repo = repo_root or Path.cwd()
    cfg = config_path or (repo / "creative.config.json")
    StudioRequestHandler.repo_root = repo.resolve()
    StudioRequestHandler.config_path = cfg.resolve()

    ThreadingHTTPServer.allow_reuse_address = True
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, StudioRequestHandler)
    print(f"🚀 App Store Creative Studio running at: http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Studio server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_studio_server()
