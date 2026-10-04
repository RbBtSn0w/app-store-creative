#!/usr/bin/env python3
"""Zero-network release validator and release-lock generator for App Store Creative v2.0."""

import hashlib
import studio_contract as contract
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


def preview_locales(config: Dict[str, Any]) -> List[str]:
    """Bind a preview to its explicitly selected project localizations."""
    project_locales = config.get("project", {}).get("locales", ["en-US"])
    locales = config.get("previewVideo", {}).get("locales", project_locales)
    if not isinstance(locales, list) or not locales or any(
        not isinstance(locale, str) or locale not in project_locales for locale in locales
    ) or len(locales) != len(set(locales)):
        raise ValueError("App Preview locales must be a nonempty unique subset of project locales")
    return locales


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


def inspect_video_file(path: Path) -> Dict[str, Any]:
    """Probe every required media field; unavailable evidence is a failure."""
    if not shutil.which("ffprobe"):
        raise ValueError("ffprobe is required to validate App Preview videos")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
         "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def declared_screenshots(config: Dict[str, Any]) -> List[str]:
    """Return the complete ordered screenshot matrix declared by the project."""
    return [f"{locale}/{target}/{card['id']}.png"
            for locale in config.get("project", {}).get("locales", ["en-US"])
            for target in config.get("targets", ["iphone_6_9"])
            for card in config.get("cards", [])]


def run_validation(
    repo_root: Path,
    config_path: Optional[Path] = None,
    artifacts_dir: Optional[Path] = None,
    write_lockfile: bool = True,
) -> Dict[str, Any]:
    # Studio saves and export publication share this lock; external writers are
    # also detected by the snapshot checks before verification is published.
    with contract.WRITE_LOCK:
        return _run_validation(repo_root, config_path, artifacts_dir, write_lockfile)


def _run_validation(repo_root, config_path, artifacts_dir, write_lockfile):
    """Validate all assets in artifacts against App Store rules, with zero network dependencies."""
    cfg_file = config_path or (repo_root / "creative.config.json")
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    config_bytes = cfg_file.read_bytes()
    config_hash = contract.digest(config_bytes)
    config = json.loads(config_bytes)
    art_dir = artifacts_dir or (repo_root / "artifacts")
    output_hashes = {str(path.relative_to(art_dir)): compute_sha256(path)
                     for pattern in ('**/*.png', '**/*.mp4') for path in art_dir.glob(pattern)}

    errors: List[str] = []
    if config.get("previewVideo", {}).get("enabled"):
        try:
            preview_locales(config)
        except ValueError as error:
            errors.append(str(error))
    asset_records: Dict[str, Any] = {}

    expected = declared_screenshots(config)
    if not expected:
        errors.append("Configuration must declare at least one screenshot")
    for name in expected:
        if not (art_dir / name).is_file():
            errors.append(f"Missing declared screenshot: {name}")
    sources, input_errors = contract.input_hashes(repo_root, config)
    capture_sources = sources.copy()
    errors.extend(input_errors)
    preview = config.get("previewVideo", {})
    if preview.get("enabled") and preview.get("source") and (repo_root / preview["source"]).is_file():
        sources[str(preview["source"])] = compute_sha256(repo_root / preview["source"])
    evidence_file = art_dir / '.export-evidence.json'
    evidence_hash = compute_sha256(evidence_file) if evidence_file.is_file() else None
    if config.get('studio', {}).get('requireExportEvidence'):
        evidence_file = art_dir / '.export-evidence.json'
        try:
            evidence = json.loads(evidence_file.read_text())
        except (OSError, ValueError):
            evidence = {}
        for name in expected:
            record = evidence.get(name, {})
            output = art_dir / name
            locale, target, _ = name.split('/')
            scoped_sources, _ = contract.input_hashes(repo_root, config, [target], [locale])
            if (record.get('config_hash') != config_hash
                or record.get('source_hashes') != scoped_sources
                or not output.is_file() or record.get('sha256') != compute_sha256(output)
                or record.get('render_ready') is not True):
                errors.append(f'Missing or stale render evidence: {name}; export the current project')
    preview = config.get("previewVideo", {})
    if preview.get("enabled"):
        source = preview.get("source")
        if not source or not (repo_root / source).is_file():
            errors.append("Enabled previewVideo requires an existing real source recording")
        if not (art_dir / "preview/app_preview.mp4").is_file():
            errors.append("Missing declared App Preview: preview/app_preview.mp4")

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

        try:
            from fractions import Fraction
            probe = inspect_video_file(mp4)
            streams = probe.get("streams", [])
            video = next((x for x in streams if x.get("codec_type") == "video"), {})
            audio = next((x for x in streams if x.get("codec_type") == "audio"), {})
            duration = float(probe["format"]["duration"])
            fps = float(Fraction(video["r_frame_rate"]))
            width, height = int(video["width"]), int(video["height"])
            if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
                raise ValueError("App Preview requires H.264 video and AAC audio")
            if not 14.95 <= duration <= 30.05 or not 0 < fps <= 30:
                raise ValueError("App Preview requires 15-30 seconds and at most 30 fps")
            is_mac = any(x.startswith("mac_") for x in config.get("targets", []))
            portrait = preview.get("orientation", "portrait") == "portrait" and not is_mac
            expected_size = (int(preview.get("width", 886 if portrait else 1920)),
                             int(preview.get("height", 1920 if portrait else (1080 if is_mac else 886))))
            if (width, height) != expected_size:
                raise ValueError(f"App Preview dimensions must be {expected_size}")
            if abs(fps - float(preview.get("fps", 30))) > .01:
                raise ValueError("App Preview fps differs from configuration")
            if preview.get("enabled") and abs(duration - float(preview.get("duration", 20))) > .05:
                raise ValueError("App Preview duration differs from configuration")
            asset_records[str(rel)] = {"sha256": sha, "type": "video", "size_bytes": size_bytes,
                                       "duration": duration, "fps": fps, "width": width, "height": height,
                                       "video_codec": video["codec_name"], "audio_codec": audio["codec_name"]}
        except Exception as exc:
            errors.append(f"Failed to validate video {rel}: {exc}")

    # Write release-lock.json
    lock_data = {
        "schema_version": 2,
        "status": "PASS" if not errors else "FAIL",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(repo_root),
        "config_hash": config_hash,
        "artifacts_dir": str(art_dir.resolve()),
        "config_path": str(cfg_file.resolve()),
        "source_hashes": sources,
        "assets_count": len(asset_records),
        "assets": asset_records,
        "errors": errors,
    }

    try:
        changed = compute_sha256(cfg_file) != config_hash
        current_sources, current_input_errors = contract.input_hashes(repo_root, config)
        changed = changed or current_sources != capture_sources or current_input_errors != input_errors
        changed = changed or any(compute_sha256(contract.local_asset(repo_root, name, config)) != sha
                                  for name, sha in sources.items())
        changed = changed or any(compute_sha256(art_dir / name) != record['sha256']
                                  for name, record in asset_records.items())
        changed = changed or output_hashes != {str(path.relative_to(art_dir)): compute_sha256(path)
            for pattern in ('**/*.png', '**/*.mp4') for path in art_dir.glob(pattern)}
        if config.get('studio', {}).get('requireExportEvidence'):
            changed = changed or (compute_sha256(evidence_file) if evidence_file.is_file() else None) != evidence_hash
    except (OSError, ValueError):
        changed = True
    if changed:
        errors.append('Configuration, sources, outputs or render evidence changed during validation; retry with stable inputs')
        lock_data['status'] = 'FAIL'

    if write_lockfile:
        lock_dir = repo_root / ".creative"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "release-lock.json"
        with contract.WRITE_LOCK:
            if lock_file.exists():
                previous = lock_file.read_bytes()
                history_file = lock_dir / 'release-history' / f'{contract.digest(previous)}.json'
                if not history_file.exists():
                    history_file.parent.mkdir(parents=True, exist_ok=True)
                    history_file.write_bytes(previous)
            contract.atomic_json(lock_file, lock_data)
        print(f"🔒 Current release evidence written to: {lock_file}")

    if errors:
        print("❌ Verification FAILED with issues:")
        for err in errors:
            print(f"   - {err}")
    else:
        print(f"✅ Verification PASSED: {len(asset_records)} assets fully compliant with Apple specifications.")

    return lock_data


if __name__ == "__main__":
    run_validation(Path.cwd())
