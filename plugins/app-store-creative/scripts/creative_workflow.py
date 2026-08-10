#!/usr/bin/env python3
"""Deterministic, local-first workflow engine for App Store creative assets."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

SCHEMA_VERSION = 1
STATE_DIR = ".app-store-creative"


class WorkflowError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, value: Any, *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        existing = path.read_bytes()
        if existing == canonical(value):
            return
        raise WorkflowError(f"immutable record already exists: {path}")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"invalid JSON: {path}: {exc}") from exc


def confined(root: Path, path: Path, label: str) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise WorkflowError(f"{label} escapes repository root: {path}")
    return resolved


@dataclass(frozen=True)
class Store:
    root: Path

    @property
    def state(self) -> Path:
        return self.root / STATE_DIR

    def require(self) -> None:
        if not (self.state / "config.json").is_file():
            raise WorkflowError(f"not initialized: {self.root}")

    def task_path(self, task_id: str) -> Path:
        return self.state / "tasks" / f"{task_id}.json"

    def append_event(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        events = self.state / "events"
        events.mkdir(parents=True, exist_ok=True)
        lock_path = self.state / "events.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            previous_files = sorted(events.glob("*.json"))
            previous = file_digest(previous_files[-1]) if previous_files else None
            sequence = len(previous_files) + 1
            body = {"schema_version": SCHEMA_VERSION, "sequence": sequence, "kind": kind,
                    "payload": payload, "previous_event_sha256": previous}
            atomic_write(events / f"{sequence:08d}-{digest(body)[:16]}.json", body, immutable=True)
        return body


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve())
    config = store.state / "config.json"
    wanted = {"schema_version": SCHEMA_VERSION, "project": args.project}
    if config.exists():
        current = load_json(config)
        if current != wanted:
            raise WorkflowError("workspace already initialized with different configuration")
        return {"initialized": False, "state": str(store.state)}
    for name in ("tasks", "claims", "receipts", "approvals", "events", "upload-plans", "runs", "releases"):
        (store.state / name).mkdir(parents=True, exist_ok=True)
    atomic_write(config, wanted)
    atomic_write(store.state / "project.json", {"schema_version": SCHEMA_VERSION, "project": args.project})
    atomic_write(store.state / "release-template.json", {"schema_version": SCHEMA_VERSION, "tasks": [{
        "kind": "screenshot", "locale": "en-US", "device": "replace-me", "output": "release-assets/example.png",
        "dimensions": [1, 1]}]})
    store.append_event("initialized", wanted)
    return {"initialized": True, "state": str(store.state)}


def normalize_task(raw: dict[str, Any], run_id: str) -> dict[str, Any]:
    required = ("kind", "locale", "device", "output")
    missing = [key for key in required if not isinstance(raw.get(key), str) or not raw[key]]
    if missing:
        raise WorkflowError(f"task missing non-empty fields: {', '.join(missing)}")
    task = {"schema_version": SCHEMA_VERSION, "run_id": run_id, **raw}
    task.pop("id", None)
    output = Path(task["output"])
    if output.is_absolute() or ".." in output.parts: raise WorkflowError("task output must stay inside the repository")
    task["output"] = str(output)
    return task


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    source = load_json(args.manifest)
    raw_tasks = source.get("tasks") if isinstance(source, dict) else source
    if not isinstance(raw_tasks, list):
        raise WorkflowError("manifest must be a task array or an object containing tasks")
    run_id = getattr(args, "run_id", None) or file_digest(args.manifest)[:16]
    ids = []
    for raw in raw_tasks:
        if not isinstance(raw, dict):
            raise WorkflowError("every task must be an object")
        body = normalize_task(raw, run_id)
        task_id = digest(body)[:24]
        atomic_write(store.task_path(task_id), {"id": task_id, **body}, immutable=True)
        ids.append(task_id)
    run = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "task_ids": ids,
           "manifest_sha256": file_digest(args.manifest)}
    atomic_write(store.state / "runs" / f"{run_id}.json", run, immutable=True)
    store.append_event("planned", run)
    return {"run_id": run_id, "task_ids": ids, "count": len(ids)}


def task_state(store: Store, task_id: str) -> str:
    if (store.state / "receipts" / f"{task_id}.json").exists(): return "complete"
    claim_path = store.state / "claims" / f"{task_id}.json"
    if claim_path.exists():
        return "expired" if load_json(claim_path)["expires_at"] <= time.time() else "claimed"
    return "pending"


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    run_id = args.run_id
    run = load_json(store.state / "runs" / f"{run_id}.json")
    tasks = [{"id": task_id, "state": task_state(store, task_id)} for task_id in run["task_ids"]]
    states = ("pending", "claimed", "expired", "complete")
    return {"run_id": run_id, "tasks": tasks, "counts": {s: sum(t["state"] == s for t in tasks) for s in states}}


def command_claim(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    if not store.task_path(args.task_id).exists(): raise WorkflowError("unknown task")
    task = load_json(store.task_path(args.task_id))
    if task["run_id"] != args.run_id: raise WorkflowError("task does not belong to run")
    if task_state(store, args.task_id) == "complete": raise WorkflowError("task already complete")
    path = store.state / "claims" / f"{args.task_id}.json"
    lock_path = store.state / "claims" / f".{args.task_id}.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if getattr(args, "release_claim", False):
            current = load_json(path)
            if current["run_id"] != args.run_id or current["owner"] != args.owner: raise WorkflowError("only the claim owner can release it")
            path.unlink(); store.append_event("claim_released", {"run_id": args.run_id, "task_id": args.task_id, "owner": args.owner})
            return {"released": True, "run_id": args.run_id, "task_id": args.task_id}
        token = uuid.uuid4().hex
        now = time.time(); ttl = args.ttl_seconds
        if ttl <= 0: raise WorkflowError("ttl must be positive")
        body = {"schema_version": SCHEMA_VERSION, "run_id": args.run_id, "task_id": args.task_id,
                "owner": args.owner, "token": token, "created_at": now, "expires_at": now + ttl, "ttl_seconds": ttl}
        if path.exists() and args.reclaim_expired:
            current = load_json(path)
            if current["expires_at"] > now: raise WorkflowError("active claim cannot be reclaimed")
            os.replace(path, path.with_suffix(f".expired-{uuid.uuid4().hex}.json"))
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise WorkflowError("task already claimed") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(body)); stream.flush(); os.fsync(stream.fileno())
    store.append_event("claimed", {"run_id": args.run_id, "task_id": args.task_id, "owner": args.owner, "expires_at": body["expires_at"]})
    return body


def inspect_png(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    header = data[:29]
    if len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise WorkflowError(f"invalid PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    color_type = header[25]
    if color_type in {4, 6}: raise WorkflowError("PNG alpha channels are not allowed for App Store screenshots")
    if color_type != 2: raise WorkflowError("PNG must use truecolor RGB")
    chunks = []
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + length
        if end > len(data): raise WorkflowError("truncated PNG chunk")
        kind = data[offset + 4:offset + 8]
        chunks.append(kind)
        offset = end
        if kind == b"IEND": break
    if not chunks or chunks[0] != b"IHDR" or chunks[-1] != b"IEND": raise WorkflowError("invalid PNG chunk structure")
    has_srgb = b"sRGB" in chunks
    has_iccp = b"iCCP" in chunks
    if not (has_srgb or has_iccp): raise WorkflowError("PNG must include sRGB or ICC profile metadata")
    return {"media_type": "image/png", "width": width, "height": height, "color_type": color_type,
            "has_alpha": False, "color_profile": "sRGB" if has_srgb else "iCCP"}


def inspect_video(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe: raise WorkflowError("ffprobe is required to validate video")
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration,format_name:stream=index,codec_type,codec_name,width,height,r_frame_rate",
                             "-of", "json", str(path)], text=True, capture_output=True)
    if result.returncode != 0: raise WorkflowError(f"invalid video: {path}: {result.stderr.strip()}")
    payload = json.loads(result.stdout); data = payload["format"]; streams = payload.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video: raise WorkflowError("video stream is required")
    rate = video.get("r_frame_rate", "0/1"); n, d = (float(x) for x in rate.split("/")); fps = n / d if d else 0
    return {"media_type": data.get("format_name"), "duration": float(data["duration"]), "codec": video.get("codec_name"),
            "width": video.get("width"), "height": video.get("height"), "fps": fps,
            "audio_codec": audio.get("codec_name") if audio else None}


def inspect_asset(path: Path) -> dict[str, Any]:
    if not path.is_file(): raise WorkflowError(f"missing asset: {path}")
    suffix = path.suffix.lower()
    info = inspect_png(path) if suffix == ".png" else inspect_video(path) if suffix in {".mp4", ".mov", ".m4v"} else None
    if info is None: raise WorkflowError(f"unsupported asset type: {suffix}")
    return {**info, "path": str(path), "size": path.stat().st_size, "sha256": file_digest(path)}


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    task = load_json(store.task_path(args.task_id))
    asset = confined(store.root, store.root / task["output"], "task output")
    if task["kind"] == "screenshot" and asset.suffix.lower() != ".png":
        raise WorkflowError("screenshot tasks require PNG assets")
    if task["kind"] == "app_preview" and asset.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
        raise WorkflowError("app_preview tasks require video assets")
    info = inspect_asset(asset)
    if task["kind"] == "screenshot" and info["media_type"] != "image/png":
        raise WorkflowError("screenshot tasks require PNG assets")
    expected = task.get("dimensions")
    if expected and [info.get("width"), info.get("height")] != expected:
        raise WorkflowError(f"dimension mismatch: expected {expected}, got {[info.get('width'), info.get('height')]}")
    contract = task.get("media_contract", {})
    for field in ("codec", "audio_codec"):
        if field in contract and info.get(field) != contract[field]: raise WorkflowError(f"{field} mismatch")
    if contract.get("audio_required") and not info.get("audio_codec"): raise WorkflowError("audio stream is required")
    for field in ("fps", "duration"):
        if field in contract and abs(info.get(field, 0) - contract[field]) > contract.get(f"{field}_tolerance", 0.01): raise WorkflowError(f"{field} mismatch")
    return {"run_id": task["run_id"], "task_id": args.task_id, "asset": info}


def command_complete(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    claim_path = store.state / "claims" / f"{args.task_id}.json"
    claim = load_json(claim_path)
    if claim["token"] != args.token: raise WorkflowError("claim token mismatch")
    if claim["expires_at"] <= time.time(): raise WorkflowError("claim expired")
    verified = command_verify(args)
    task = load_json(store.task_path(args.task_id))
    producer_receipt = load_json(args.producer_receipt)
    body = {"schema_version": SCHEMA_VERSION, "run_id": task["run_id"], "task_id": args.task_id, "task_sha256": file_digest(store.task_path(args.task_id)),
            "asset": verified["asset"], "claim": {"owner": claim["owner"], "token_sha256": hashlib.sha256(args.token.encode()).hexdigest()}}
    body["producer_receipt"] = producer_receipt
    body["producer_receipt_sha256"] = file_digest(args.producer_receipt)
    body["receipt_sha256"] = digest(body)
    atomic_write(store.state / "receipts" / f"{args.task_id}.json", body, immutable=True)
    claim_path.unlink()
    store.append_event("completed", {"task_id": args.task_id, "receipt_sha256": body["receipt_sha256"]})
    return body


def command_approve(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    receipt_path = store.state / "receipts" / f"{args.task_id}.json"
    if not receipt_path.exists(): raise WorkflowError("task is not complete")
    receipt = load_json(receipt_path)
    if args.approver == receipt["claim"]["owner"]: raise WorkflowError("self approval is forbidden")
    if args.stage == "upload":
        design = approval(store, args.task_id, "design")
        if args.approver == design["approver"]: raise WorkflowError("upload approver must differ from design approver")
    body = {"schema_version": SCHEMA_VERSION, "task_id": args.task_id, "stage": args.stage,
            "approver": args.approver, "receipt_sha256": file_digest(receipt_path),
            "input_sha256": args.input_sha256}
    body["approval_sha256"] = digest(body)
    directory = store.state / "approvals" / f"{args.task_id}-{args.stage}"
    atomic_write(directory / f"{body['approval_sha256']}.json", body, immutable=True)
    atomic_write(directory / "current.json", {"approval_sha256": body["approval_sha256"]})
    store.append_event("approved", {"task_id": args.task_id, "stage": args.stage, "approval_sha256": body["approval_sha256"]})
    return body


def approval(store: Store, task_id: str, stage: str) -> dict[str, Any]:
    directory = store.state / "approvals" / f"{task_id}-{stage}"
    pointer = load_json(directory / "current.json")
    result = load_json(directory / f"{pointer['approval_sha256']}.json")
    claimed = result.get("approval_sha256"); unsigned = {key: value for key, value in result.items() if key != "approval_sha256"}
    if claimed != digest(unsigned) or claimed != pointer["approval_sha256"]: raise WorkflowError(f"invalid {stage} approval history")
    receipt_path = store.state / "receipts" / f"{task_id}.json"
    if result["receipt_sha256"] != file_digest(receipt_path): raise WorkflowError(f"stale {stage} approval")
    return result


def command_promote(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require(); approval(store, args.task_id, "design")
    receipt = load_json(store.state / "receipts" / f"{args.task_id}.json")
    body = {"schema_version": SCHEMA_VERSION, "task_id": args.task_id, "receipt_sha256": file_digest(store.state / "receipts" / f"{args.task_id}.json")}
    atomic_write(store.state / "receipts" / f"{args.task_id}-promotion.json", body, immutable=True)
    store.append_event("promoted", body)
    return {**body, "asset": receipt["asset"]}


def promote_release(root: Path, run_id: str, input_dir: Path) -> dict[str, Any]:
    """Atomically promote all run assets, restoring prior destinations on failure."""
    store = Store(root.resolve()); store.require()
    run = load_json(store.state / "runs" / f"{run_id}.json")
    staging = Path(tempfile.mkdtemp(prefix="promotion-", dir=store.state))
    prepared: list[tuple[str, Path, Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    try:
        for task_id in run["task_ids"]:
            design = approval(store, task_id, "design")
            if design["input_sha256"] != run["manifest_sha256"]: raise WorkflowError("design approval is not bound to this release manifest")
            task = load_json(store.task_path(task_id))
            source = confined(store.root, input_dir / Path(task["output"]), "promotion source")
            verified = inspect_asset(source)
            receipt = load_json(store.state / "receipts" / f"{task_id}.json")
            if verified["sha256"] != receipt["asset"]["sha256"]: raise WorkflowError(f"promotion asset hash mismatch: {task_id}")
            staged = staging / task_id / source.name; staged.parent.mkdir(parents=True); shutil.copy2(source, staged)
            destination = confined(store.root, store.root / task["output"], "promotion destination")
            prepared.append((task_id, staged, destination, source))
        for task_id, staged, destination, _ in prepared:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                backup = staging / "backups" / task_id; backup.parent.mkdir(parents=True, exist_ok=True); os.replace(destination, backup); backups.append((backup, destination))
            os.replace(staged, destination)
        assets = [{"task_id": task_id, "path": str(destination), "sha256": file_digest(destination)} for task_id, _, destination, _ in prepared]
        manifest = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "assets": assets}
        manifest["manifest_sha256"] = digest(manifest)
        atomic_write(store.state / "releases" / f"{run_id}.json", manifest, immutable=True)
        store.append_event("release_promoted", {"run_id": run_id, "manifest_sha256": manifest["manifest_sha256"]})
        return manifest
    except Exception:
        for _, _, destination, _ in reversed(prepared):
            if destination.exists() and not any(d == destination for _, d in backups): destination.unlink()
        for backup, destination in reversed(backups):
            if backup.exists(): os.replace(backup, destination)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def command_upload_plan(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    design = approval(store, args.task_id, "design")
    verified = command_verify(args)
    receipt_path = store.state / "receipts" / f"{args.task_id}.json"
    body = {"schema_version": SCHEMA_VERSION, "task_id": args.task_id, "receipt_sha256": file_digest(receipt_path),
            "asset_sha256": verified["asset"]["sha256"], "design_approval_sha256": design["approval_sha256"],
            "mutation": "replace_app_store_creative"}
    body["plan_id"] = digest(body)[:24]
    atomic_write(store.state / "upload-plans" / f"{body['plan_id']}.json", body, immutable=True)
    store.append_event("upload_planned", {"task_id": args.task_id, "plan_id": body["plan_id"]})
    return body


class UploadAdapter(Protocol):
    def upload(self, plan: dict[str, Any]) -> dict[str, Any]: ...


def command_upload(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    plan = load_json(store.state / "upload-plans" / f"{args.plan_id}.json")
    approval(store, plan["task_id"], "design"); upload = approval(store, plan["task_id"], "upload")
    if upload["input_sha256"] != args.plan_sha256: raise WorkflowError("upload approval is not bound to this plan")
    if not args.execute:
        return {"executed": False, "plan": plan, "message": "dry-run; pass --execute with an installed adapter"}
    raise WorkflowError("no upload adapter installed; no external mutation was performed")


def command_audit(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require()
    problems = []
    previous = None
    for expected, path in enumerate(sorted((store.state / "events").glob("*.json")), 1):
        event = load_json(path)
        if event.get("sequence") != expected: problems.append(f"event sequence mismatch: {path.name}")
        if event.get("previous_event_sha256") != previous: problems.append(f"event chain mismatch: {path.name}")
        previous = file_digest(path)
    for receipt in sorted((store.state / "receipts").glob("*.json")):
        if receipt.name.endswith("-promotion.json"): continue
        body = load_json(receipt); claimed = body.pop("receipt_sha256", None)
        if claimed != digest(body): problems.append(f"receipt digest mismatch: {receipt.name}")
    return {"ok": not problems, "problems": problems}


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve(); state = root / STATE_DIR
    return {"python": sys.version.split()[0], "python_ok": sys.version_info >= (3, 10), "root": str(root),
            "initialized": (state / "config.json").is_file(), "sips": shutil.which("sips"), "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"), "asc": shutil.which("asc")}


def command_upgrade(args: argparse.Namespace) -> dict[str, Any]:
    store = Store(args.root.resolve()); store.require(); config = load_json(store.state / "config.json")
    version = config.get("schema_version", 0)
    if version > SCHEMA_VERSION: raise WorkflowError("workspace schema is newer than this CLI")
    if version == SCHEMA_VERSION: return {"upgraded": False, "schema_version": version}
    raise WorkflowError(f"no migration available from schema version {version}")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app-store-creative")
    p.add_argument("--root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("doctor"); d.set_defaults(func=command_doctor)
    i = sub.add_parser("init"); i.add_argument("--project", required=True); i.set_defaults(func=command_init)
    pl = sub.add_parser("plan"); pl.add_argument("manifest", type=Path); pl.set_defaults(func=command_plan)
    s = sub.add_parser("status"); s.set_defaults(func=command_status)
    c = sub.add_parser("claim"); c.add_argument("task_id"); c.add_argument("--owner", required=True); c.set_defaults(func=command_claim)
    for name, func in (("verify", command_verify), ("promote", command_promote)):
        x = sub.add_parser(name); x.add_argument("task_id"); x.set_defaults(func=func)
    co = sub.add_parser("complete"); co.add_argument("task_id"); co.add_argument("--token", required=True); co.set_defaults(func=command_complete)
    ap = sub.add_parser("approve"); ap.add_argument("task_id"); ap.add_argument("--stage", choices=("design", "upload"), required=True); ap.add_argument("--approver", required=True); ap.set_defaults(func=command_approve)
    up = sub.add_parser("upload-plan"); up.add_argument("task_id"); up.set_defaults(func=command_upload_plan)
    u = sub.add_parser("upload"); u.add_argument("plan_id"); u.add_argument("--execute", action="store_true"); u.set_defaults(func=command_upload)
    a = sub.add_parser("audit"); a.set_defaults(func=command_audit)
    g = sub.add_parser("upgrade"); g.set_defaults(func=command_upgrade)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = args.func(args)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0 if result.get("ok", True) else 2
    except WorkflowError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
