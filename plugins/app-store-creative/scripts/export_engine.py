#!/usr/bin/env python3
"""Headless 1:1 Pixel Export Engine for App Store Creative v2.0."""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from studio_server import StudioRequestHandler, ThreadingHTTPServer
except ImportError:
    from .studio_server import StudioRequestHandler, ThreadingHTTPServer


# Standard Apple App Store Connect Dimensions
TARGET_SPECS: Dict[str, Dict[str, any]] = {
    "iphone_6_9": {"width": 1320, "height": 2868, "display_name": 'iPhone 16 Pro Max (6.9")'},
    "iphone_6_7": {"width": 1290, "height": 2796, "display_name": 'iPhone 15 Pro Max (6.7")'},
    "iphone_6_5": {"width": 1242, "height": 2688, "display_name": 'iPhone 11 Pro Max (6.5")'},
    "iphone_5_5": {"width": 1242, "height": 2208, "display_name": 'iPhone 8 Plus (5.5")'},
    "ipad_13": {"width": 2064, "height": 2752, "display_name": 'iPad Pro 13" M4'},
    "ipad_12_9": {"width": 2048, "height": 2732, "display_name": 'iPad Pro 12.9"'},
    "mac_16_10": {"width": 2880, "height": 1800, "display_name": "MacBook Pro 16:10"},
    "watch_ultra": {"width": 410, "height": 502, "display_name": "Apple Watch Ultra"},
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

    def __init__(self, repo_root: Path, config_path: Path, port: Optional[int] = None):
        self.repo_root = repo_root
        self.config_path = config_path
        self.port = port or find_free_port(3100)
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def __enter__(self):
        StudioRequestHandler.repo_root = self.repo_root.resolve()
        StudioRequestHandler.config_path = self.config_path.resolve()
        ThreadingHTTPServer.allow_reuse_address = True
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), StudioRequestHandler)
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


def export_single_card(
    chrome_bin: str,
    port: int,
    card_id: str,
    target: str,
    locale: str,
    output_path: Path,
    timeout_seconds: int = 45,
) -> bool:
    """Render a single card at 1:1 physical pixel dimensions via headless Chrome."""
    spec = TARGET_SPECS.get(target, TARGET_SPECS["iphone_6_9"])
    width = spec["width"]
    height = spec["height"]

    url = f"http://127.0.0.1:{port}/?export=true&card={card_id}&target={target}&locale={locale}"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_bin,
        "--headless=new",
        f"--screenshot={output_path.resolve()}",
        f"--window-size={width},{height}",
        "--default-background-color=00000000",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1000",
        url,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        print(f"❌ Timed out exporting {card_id} for {target} after {timeout_seconds}s", file=sys.stderr)
        return False

    if not output_path.exists() or output_path.stat().st_size == 0:
        print(f"❌ Failed to export {card_id} for {target}: {res.stderr}", file=sys.stderr)
        return False

    # Optional: ensure standard PNG metadata if sips is present
    if shutil.which("sips"):
        subprocess.run(["sips", "-s", "format", "png", str(output_path)], capture_output=True)

    return True


def run_export(
    repo_root: Path,
    config_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    targets: Optional[List[str]] = None,
    locales: Optional[List[str]] = None,
) -> Dict[str, any]:
    """Execute complete batch export of all cards across targets and locales."""
    cfg_file = config_path or (repo_root / "creative.config.json")
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    config = json.loads(cfg_file.read_text())
    chrome = find_chrome_binary()
    if not chrome:
        raise RuntimeError("No compatible Chrome/Chromium executable found on this system.")

    out_root = output_dir or (repo_root / "artifacts")
    active_targets = targets or config.get("targets", ["iphone_6_9"])
    active_locales = locales or config.get("project", {}).get("locales", ["en-US"])
    cards = config.get("cards", [])

    print(f"📦 Starting Headless Export using: {chrome}")
    print(f"🎯 Targets: {', '.join(active_targets)}")
    print(f"🌐 Locales: {', '.join(active_locales)}")
    print(f"🖼  Cards: {len(cards)}")

    results = []
    start_time = time.time()

    with LocalServerContext(repo_root, cfg_file) as ctx:
        for locale in active_locales:
            for target in active_targets:
                for card in cards:
                    card_id = card["id"]
                    dest = out_root / locale / target / f"{card_id}.png"
                    print(f"   ↳ Rendering [{locale}] [{target}] {card_id}...", end="", flush=True)

                    success = export_single_card(
                        chrome_bin=chrome,
                        port=ctx.port,
                        card_id=card_id,
                        target=target,
                        locale=locale,
                        output_path=dest,
                    )
                    if success:
                        size_kb = dest.stat().st_size / 1024
                        print(f" ✅ ({size_kb:.1f} KB)")
                        results.append({"card_id": card_id, "target": target, "locale": locale, "path": str(dest)})
                    else:
                        print(" ❌")

    elapsed = time.time() - start_time
    print(f"\n✨ Export complete: {len(results)} assets rendered in {elapsed:.2f}s to {out_root}")
    return {"total_rendered": len(results), "elapsed_seconds": elapsed, "artifacts": results}


if __name__ == "__main__":
    repo = Path.cwd()
    run_export(repo)
