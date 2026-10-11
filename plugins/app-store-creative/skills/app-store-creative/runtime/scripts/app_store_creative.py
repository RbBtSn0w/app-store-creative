#!/usr/bin/env python3
"""Stable command-line interface for the local App Store creative workflow (v2.0)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit("App Store Creative requires Python 3.11 or newer")

# Ensure script directory is in sys.path for direct script imports
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

import lifecycle_commands
import production_lifecycle
import studio_server


def run(args):
    root = (args.repo or Path.cwd()).resolve()
    def project_path(value):
        return (value if value.is_absolute() else root / value).resolve() if value else None

    if args.command in ("history", "preview", "run", "attempt", "artifact", "candidate", "inventory", "storage", "approval", "delivery", "archive", "publication", "cleanup", "incident", "input"):
        return lifecycle_commands.execute(args)

    # Modern v2 commands
    if args.command in ("dev", "studio"):
        cfg = project_path(getattr(args, "config", None))
        studio_server.run_studio_server(port=args.port, repo_root=root, config_path=cfg)
        return {"status": "ok", "message": f"Studio stopped on port {args.port}"}

    if args.command == "export":
        if getattr(args, 'output_dir', None):
            raise ValueError('export --output-dir is unsupported for managed attempts; configure storage.workspaceRoot in creative.config.json instead (and storage.objectRoot for retained media)')
        cfg = project_path(getattr(args, 'config', None))
        return production_lifecycle.produce(root, cfg, targets=getattr(args, 'targets', None),
            locales=getattr(args, 'locales', None), with_video=getattr(args, 'with_video', False))

    raise AssertionError(args.command)


def build_parser():
    p = argparse.ArgumentParser(description="App Store Creative CLI (v2.0)")
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name):
        x = sub.add_parser(name)
        x.add_argument("--repo", type=Path, default=Path.cwd())
        return x

    lifecycle_commands.add_commands(sub)

    # Modern v2 Subcommands
    for name in ("dev", "studio"):
        dev = cmd(name)
        dev.add_argument("--config", type=Path, help="Path to creative.config.json")
        dev.add_argument("--port", type=int, default=3100, help="Local studio port (default 3100)")

    exp = cmd("export")
    exp.add_argument("--config", type=Path, help="Path to creative.config.json")
    exp.add_argument("--output-dir", type=Path, help="Unsupported for managed export; configure storage.workspaceRoot in creative.config.json instead")
    exp.add_argument("--target", action="append", dest="targets", help="Specific target to export (repeatable)")
    exp.add_argument("--locale", action="append", dest="locales", help="Specific locale to export (repeatable)")
    exp.add_argument("--with-video", action="store_true", help="Also synthesize App Preview video")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        res = run(args)
        if res is not None:
            print(json.dumps(res, sort_keys=True, ensure_ascii=False, indent=2))
        # Ensure CI gates fail if validation reported FAIL
        if isinstance(res, dict) and res.get("status") == "FAIL":
            return 2
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
