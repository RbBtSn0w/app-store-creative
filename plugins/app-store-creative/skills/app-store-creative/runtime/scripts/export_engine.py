#!/usr/bin/env python3
"""Headless 1:1 Pixel Export Engine for App Store Creative v2.0."""

import json
import html
import re
import tempfile
import urllib.parse
import studio_contract as contract
import os
import shutil
import socket
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from studio_server import make_handler, ThreadingHTTPServer
except ImportError:
    from .studio_server import make_handler, ThreadingHTTPServer


# Standard Apple App Store Connect Dimensions
TARGET_SPECS: Dict[str, Dict[str, Any]] = {
    "iphone_6_9": {"width": 1320, "height": 2868, "display_name": 'iPhone 16 Pro Max (6.9")'},
    "iphone_6_7": {"width": 1290, "height": 2796, "display_name": 'iPhone 15 Pro Max (6.7")'},
    "iphone_6_5": {"width": 1242, "height": 2688, "display_name": 'iPhone 11 Pro Max (6.5")'},
    "iphone_5_5": {"width": 1242, "height": 2208, "display_name": 'iPhone 8 Plus (5.5")'},
    "ipad_13": {"width": 2064, "height": 2752, "display_name": 'iPad Pro 13" M4'},
    "ipad_12_9": {"width": 2048, "height": 2732, "display_name": 'iPad Pro 12.9"'},
    "mac_16_10": {"width": 2880, "height": 1800, "display_name": "MacBook Pro 16:10"},
    "watch_ultra": {"width": 410, "height": 502, "display_name": "Apple Watch Ultra"},
    "google_play_phone": {"width": 1080, "height": 2400, "display_name": "Google Play Phone (9:20)"},
    "google_play_tablet_7": {"width": 1200, "height": 1920, "display_name": 'Google Play 7" Tablet'},
    "google_play_tablet_10": {"width": 1600, "height": 2560, "display_name": 'Google Play 10" Tablet'},
    "google_play_feature_graphic": {"width": 1024, "height": 500, "display_name": "Google Play Feature Graphic (1024x500)"},
}


def find_free_port(start_port: int = 3100) -> int:
    """Find an available local TCP port starting from start_port."""
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def find_chrome_binary() -> Optional[str]:
    """Find local Chrome, Brave, Edge, or Chromium executable."""
    if os.environ.get("CHROME_PATH") and os.path.exists(os.environ["CHROME_PATH"]):
        return os.environ["CHROME_PATH"]

    mac_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for c in mac_candidates:
        if os.path.exists(c):
            return c

    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        found = shutil.which(name)
        if found:
            return found

    return None


class LocalServerContext:
    """Manages background studio server during export with health polling."""

    def __init__(self, repo_root: Path, config_path: Path, port: Optional[int] = None, config_bytes=None, asset_bytes=None):
        self.config_bytes = config_bytes
        self.asset_bytes = asset_bytes
        self.repo_root = repo_root
        self.config_path = config_path
        self.port = port or find_free_port(3100)
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def __enter__(self):
        handler = make_handler(self.repo_root, self.config_path, self.config_bytes, self.asset_bytes)
        ThreadingHTTPServer.allow_reuse_address = True
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        # Health probe polling instead of arbitrary sleep
        health_url = f"http://127.0.0.1:{self.port}/api/health"
        server_ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(health_url, timeout=0.2) as resp:
                    if resp.status == 200:
                        server_ready = True
                        break
            except Exception:
                time.sleep(0.05)

        if not server_ready:
            raise RuntimeError(f"Studio server failed to become ready on port {self.port}")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def stop_owned_browser(profile: Path):
    """Stop only processes carrying this launch's unique temporary profile."""
    identity = re.compile(r'(?<!\S)--user-data-dir=' + re.escape(str(profile)) + r'(?!\S)')
    def owned_pids():
        listing = subprocess.run(['/bin/ps', '-ww', '-axo', 'pid=,stat=,args='], capture_output=True, text=True, timeout=5)
        owned = []
        for line in listing.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) == 3 and 'Z' not in parts[1] and identity.search(parts[2]):
                owned.append(int(parts[0]))
        return owned
    for pid in owned_pids():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not owned_pids():
            return
        time.sleep(0.05)
    for pid in owned_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_native_browser(cmd, profile: Path, output: Path, timeout_seconds: int):
    """Capture the canonical page only after actual images, fonts, and layout settle."""
    import chrome_renderer
    try:
        return chrome_renderer.render_native(cmd, profile, output, timeout_seconds)
    finally:
        stop_owned_browser(profile)



def export_single_card(
    chrome_bin: str,
    port: int,
    card_id: str,
    target: str,
    locale: str,
    output_path: Path,
    timeout_seconds: int = 45,
    diagnostics=None,
    metadata=None,
) -> bool:
    """Render a single card at 1:1 physical pixel dimensions via headless Chrome."""
    spec = TARGET_SPECS.get(target, TARGET_SPECS["iphone_6_9"])
    width = spec["width"]
    height = spec["height"]

    url = f"http://127.0.0.1:{port}/?" + urllib.parse.urlencode({"export": "true", "card": card_id, "target": target, "locale": locale})
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_bin,
        "--headless=new",
        f"--screenshot={output_path.resolve()}",
        f"--window-size={width},{height}",
        "--default-background-color=ffffffff",
        "--dump-dom",
        "--no-first-run",
        "--disable-background-networking",
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=10000",
        url,
    ]

    def fail(message):
        if diagnostics is not None:
            diagnostics.append(message)
        print(message, file=sys.stderr)
        return False

    try:
        with tempfile.TemporaryDirectory(prefix='creative-chrome-', ignore_cleanup_errors=True) as profile:
            cmd.insert(1, f'--user-data-dir={profile}')
            if sys.platform == 'darwin' and any(parent.suffix == '.app' for parent in Path(chrome_bin).parents):
                res = run_native_browser(cmd, Path(profile), output_path, timeout_seconds)
            else:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except (subprocess.TimeoutExpired, TimeoutError):
        return fail(f"Browser timed out after {timeout_seconds}s; retry after checking Chrome can start locally")
    except (OSError, ValueError, RuntimeError) as error:
        return fail(f'Browser render failed: {error}; review the affected card and retry')

    if res.returncode or 'data-export-ready="true"' not in res.stdout:
        reason = re.search(r'data-export-error="([^"]+)"', res.stdout)
        return fail(html.unescape(reason.group(1)) if reason else (
            f'Browser exited with code {res.returncode}' if res.returncode else 'Images or fonts did not become ready'))
    if not output_path.exists() or output_path.stat().st_size == 0:
        print(f"❌ Failed to export {card_id} for {target}: {res.stderr}", file=sys.stderr)
        return False

    # Optional: ensure standard PNG metadata if sips is present
    if shutil.which("sips"):
        subprocess.run(["sips", "-s", "format", "png", str(output_path)], capture_output=True)

    try:
        w, h, alpha = contract.inspect_png(output_path.read_bytes())
        if (w, h) != (width, height) or alpha:
            raise ValueError('Output dimensions or RGB format do not match target')
    except ValueError as error:
        return fail(str(error))
    if metadata is not None:
        metadata['browser_identity'] = getattr(res, 'browser_identity', {'status': 'UNKNOWN'})
        if isinstance(getattr(res, 'geometry', None), dict):
            metadata['geometry'] = res.geometry
    return True


def run_export(
    repo_root: Path,
    config_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    targets: Optional[List[str]] = None,
    locales: Optional[List[str]] = None,
    progress=None,
    expected_revision=None,
) -> Dict[str, Any]:
    """Export one reviewed input snapshot and record per-output provenance."""
    repo_root = repo_root.resolve()
    cfg_file = config_path or (repo_root / 'creative.config.json')
    config_bytes = cfg_file.read_bytes()
    if expected_revision is not None and expected_revision != '"' + contract.digest(config_bytes) + '"':
        raise ValueError('Project changed after review; save and export again')
    config = contract.check_config(json.loads(config_bytes))
    chrome = find_chrome_binary()
    if not chrome:
        raise RuntimeError('Install Chrome or Chromium before exporting')
    active_targets = targets or config.get('targets', ['iphone_6_9'])
    active_locales = locales or config.get('project', {}).get('locales', ['en-US'])
    if any(t not in config.get('targets', ['iphone_6_9']) or t not in TARGET_SPECS for t in active_targets):
        raise ValueError('Choose a declared supported target')
    if any(l not in config.get('project', {}).get('locales', ['en-US']) for l in active_locales):
        raise ValueError('Choose a declared locale')
    sources, findings = contract.input_hashes(repo_root, config, active_targets, active_locales)
    if findings:
        return {'status': 'FAIL', 'errors': findings, 'total_rendered': 0, 'artifacts': []}
    asset_bytes = {name: (repo_root / name).read_bytes() for name in sources}
    if any(contract.digest(data) != sources[name] for name, data in asset_bytes.items()):
        raise ValueError('Source changed while preparing export; review and retry')
    out_root = output_dir or (repo_root / 'artifacts')
    out_root.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    total = len(active_targets) * len(active_locales) * len(config['cards'])
    if not total:
        raise ValueError('Add at least one card before exporting')
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='creative-export-') as directory:
        stage = Path(directory)
        with LocalServerContext(repo_root, cfg_file, config_bytes=config_bytes, asset_bytes=asset_bytes) as ctx:
            for locale in active_locales:
                for target in active_targets:
                    for card in config['cards']:
                        name = f"{locale}/{target}/{card['id']}.png"
                        dest = stage / name
                        diagnostics, metadata = [], {}
                        ok = export_single_card(chrome_bin=chrome, port=ctx.port,
                            card_id=card['id'], target=target, locale=locale, output_path=dest, diagnostics=diagnostics, metadata=metadata)
                        if ok:
                            results.append({'card_id': card['id'], 'target': target, 'locale': locale,
                                            'path': str(out_root / name), 'name': name, 'render_geometry': metadata.get('geometry'),
                                            'browser_identity': metadata.get('browser_identity', {'status': 'UNKNOWN'})})
                        else:
                            errors.append(f"{name}: {'; '.join(diagnostics) or 'Rendering failed; check images, fonts, and layout'}")
                        if progress:
                            progress(len(results) + len(errors), total, name)
        with contract.WRITE_LOCK:
            current_sources, current_findings = contract.input_hashes(repo_root, config, active_targets, active_locales)
            if cfg_file.read_bytes() != config_bytes or current_sources != sources or current_findings:
                errors.append('Inputs changed during export; save, review, and export again')
                results = []
            if not errors:
                evidence_path = out_root / '.export-evidence.json'
                try:
                    evidence = json.loads(evidence_path.read_text())
                except (OSError, ValueError):
                    evidence = {}
                for result in results:
                    name = result['name']
                    output = out_root / name
                    if not output.resolve().is_relative_to(out_root.resolve()):
                        raise ValueError('Output path escapes artifacts directory')
                    output.parent.mkdir(parents=True, exist_ok=True)
                    # Same-filesystem atomic replacement retains prior valid outputs on failures.
                    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
                        temp_path = Path(temporary.name)
                        temporary.write((stage / name).read_bytes())
                    temp_path.replace(output)
                    evidence[name] = {'config_hash': contract.digest(config_bytes), 'source_hashes': contract.input_hashes(repo_root, config, [result['target']], [result['locale']])[0],
                                      'sha256': contract.digest(output.read_bytes()), 'render_ready': True,
                                      'render_geometry': result.get('render_geometry'),
                                      'browser_identity': result.get('browser_identity', {'status': 'UNKNOWN'})}
                contract.atomic_json(evidence_path, evidence)
            else:
                results = []
    return {'status': 'FAIL' if errors else 'PASS', 'errors': errors, 'total_rendered': len(results),
            'elapsed_seconds': time.monotonic() - started, 'artifacts': results}


if __name__ == "__main__":
    repo = Path.cwd()
    run_export(repo)
