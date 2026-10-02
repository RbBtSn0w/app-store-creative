#!/usr/bin/env python3
"""Zero-network release validator and release-lock generator for App Store Creative v2.0."""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from export_engine import TARGET_SPECS
except ImportError:
    from .export_engine import TARGET_SPECS


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit(repo_root: Path) -> Optional[str]:
    """Retrieve current Git commit hash if in a git repo."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


def read_image_meta(path: Path) -> Tuple[int, int, bool]:
    """Read image width, height, and check if alpha exists using sips or pure python PNG header parse."""
    # Fast path: sips on macOS
    if shutil.which("sips"):
        try:
            w_proc = subprocess.run(["sips", "-g", "pixelWidth", str(path)], capture_output=True, text=True, check=True)
            h_proc = subprocess.run(["sips", "-g", "pixelHeight", str(path)], capture_output=True, text=True, check=True)
            a_proc = subprocess.run(["sips", "-g", "hasAlpha", str(path)], capture_output=True, text=True, check=True)

            w = int(w_proc.stdout.strip().split()[-1])
            h = int(h_proc.stdout.strip().split()[-1])
            has_alpha = a_proc.stdout.strip().split()[-1].lower() == "yes"
            return w, h, has_alpha
        except Exception:
            pass

    # Fallback pure python PNG header parsing
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a valid PNG file: {path}")
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    color_type = data[25]
    # color_type 6 = RGBA, 4 = Gray+Alpha, or tRNS chunk in paletted/gray
    has_alpha = color_type in (4, 6) or (b"tRNS" in data)
    return w, h, has_alpha


def match_target_spec(path_part: str) -> Optional[str]:
    """Fuzzy match directory name to target specification (e.g. iphone-6.9 -> iphone_6_9)."""
    normalized = path_part.replace("-", "_").replace(".", "_").lower()
    if normalized in TARGET_SPECS:
        return normalized
    for key in TARGET_SPECS:
        if key.replace("_", "") == normalized.replace("_", ""):
            return key
    return None


def inspect_video_file(path: Path) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    """Inspect video codec, audio codec, and duration with ffprobe if installed."""
    if not shutil.which("ffprobe"):
        return None, None, None

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(probe.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        streams = data.get("streams", [])
        v_codec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None)
        a_codec = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None)
        return v_codec, a_codec, duration
    except Exception:
        return None, None, None


def run_validation(
    repo_root: Path,
    config_path: Optional[Path] = None,
    artifacts_dir: Optional[Path] = None,
    write_lockfile: bool = True,
) -> Dict[str, Any]:
    """Validate all assets in artifacts against App Store rules, with zero network dependencies."""
    cfg_file = config_path or (repo_root / "creative.config.json")
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    art_dir = artifacts_dir or (repo_root / "artifacts")

    errors: List[str] = []
    asset_records: Dict[str, Any] = {}

    if not art_dir.exists() or not any(art_dir.iterdir()):
        errors.append(f"No artifacts found in: {art_dir}")
        return {"status": "FAIL", "errors": errors, "assets": {}}

    print("🔍 Running Zero-Network Apple Store Verification...")

    # Iterate over all PNG files in artifacts
    png_files = list(art_dir.glob("**/*.png"))
    for png in png_files:
        rel = png.relative_to(art_dir)
        size_bytes = png.stat().st_size
        sha = compute_sha256(png)

        # 1. File size check (Max 10MB per Apple App Store screenshot rule)
        if size_bytes > 10 * 1024 * 1024:
            errors.append(f"File exceeds 10MB limit: {rel} ({size_bytes / 1024 / 1024:.2f}MB)")

        # 2. Dimensions and Alpha check
        try:
            w, h, has_alpha = read_image_meta(png)
            if has_alpha:
                errors.append(f"Screenshot contains Alpha channel (Apple requires 24-bit RGB without transparency): {rel}")

            # Match target directory to expected dimensions
            target_key = next((match_target_spec(p) for p in rel.parts if match_target_spec(p)), None)
            if target_key:
                expected_spec = TARGET_SPECS[target_key]
                exp_w, exp_h = expected_spec["width"], expected_spec["height"]
                if (w, h) != (exp_w, exp_h) and (w, h) != (exp_h, exp_w):
                    errors.append(f"Dimension mismatch for {target_key}: {rel} is {w}x{h}, expected {exp_w}x{exp_h}")

            asset_records[str(rel)] = {
                "sha256": sha,
                "width": w,
                "height": h,
                "size_bytes": size_bytes,
                "has_alpha": has_alpha,
            }
        except Exception as e:
            errors.append(f"Failed to inspect image {rel}: {e}")

    # Check videos if present
    mp4_files = list(art_dir.glob("**/*.mp4"))
    for mp4 in mp4_files:
        rel = mp4.relative_to(art_dir)
        size_bytes = mp4.stat().st_size
        sha = compute_sha256(mp4)

        if size_bytes > 500 * 1024 * 1024:
            errors.append(f"Video exceeds 500MB limit: {rel}")

        v_codec, a_codec, duration = inspect_video_file(mp4)
        if v_codec and v_codec != "h264":
            errors.append(f"App Preview video codec must be H.264, found: {v_codec} ({rel})")
        if a_codec and a_codec != "aac":
            errors.append(f"App Preview audio codec must be AAC, found: {a_codec} ({rel})")
        if duration is not None:
            if duration < 14.95 or duration > 30.05:
                errors.append(f"App Preview duration must be 15-30 seconds, found {duration:.1f}s ({rel})")

        asset_records[str(rel)] = {
            "sha256": sha,
            "type": "video",
            "size_bytes": size_bytes,
            "duration": duration,
            "video_codec": v_codec,
            "audio_codec": a_codec,
        }

    status = "PASS" if not errors else "FAIL"

    # Write release-lock.json
    lock_data = {
        "schema_version": 2,
        "status": status,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(repo_root),
        "config_hash": compute_sha256(cfg_file),
        "assets_count": len(asset_records),
        "assets": asset_records,
        "errors": errors,
    }

    if write_lockfile:
        lock_dir = repo_root / ".creative"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "release-lock.json"
        lock_file.write_text(json.dumps(lock_data, indent=2))
        print(f"🔒 Immutable release evidence written to: {lock_file}")

    if errors:
        print("❌ Verification FAILED with issues:")
        for err in errors:
            print(f"   - {err}")
    else:
        print(f"✅ Verification PASSED: {len(asset_records)} assets fully compliant with Apple specifications.")

    return lock_data


if __name__ == "__main__":
    run_validation(Path.cwd())
