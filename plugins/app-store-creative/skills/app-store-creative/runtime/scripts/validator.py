#!/usr/bin/env python3
"""Read-only media probes for managed candidate validation."""

import hashlib
import studio_contract as contract
import json
import os
import re
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


def probe_png_format(data: bytes) -> Dict[str, Any]:
    """Inspect PNG header chunks to extract exact width, height, bit_depth, color_type, and alpha presence."""
    if len(data) < 24 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError("Invalid PNG header")
    import struct
    ihdr_len = int.from_bytes(data[8:12], 'big')
    ihdr_type = data[12:16]
    if ihdr_type != b'IHDR' or ihdr_len != 13:
        raise ValueError("Invalid PNG IHDR chunk")
    width, height, bit_depth, color_type = struct.unpack('>IIBB', data[16:26])
    has_alpha_channel = color_type in (4, 6)
    has_trns = False
    offset = 8
    while offset + 8 <= len(data):
        chunk_len = int.from_bytes(data[offset:offset+4], 'big')
        chunk_type = data[offset+4:offset+8]
        if chunk_type == b'tRNS':
            has_trns = True
            break
        if chunk_type == b'IEND':
            break
        offset += 12 + chunk_len
    has_alpha = has_alpha_channel or has_trns
    mode = {0: 'L', 2: 'RGB', 3: 'P', 4: 'LA', 6: 'RGBA'}.get(color_type, 'UNKNOWN')
    return {
        'width': width,
        'height': height,
        'bit_depth': bit_depth,
        'color_type': color_type,
        'mode': mode,
        'has_alpha': has_alpha,
    }


def read_image_meta(path: Path) -> Tuple[int, int, bool]:
    """Validate PNG chunks and pixel data before returning image metadata."""
    data = path.read_bytes()
    w, h, has_alpha = contract.inspect_png(data)
    probe = probe_png_format(data)
    if probe['has_alpha']:
        has_alpha = True
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


def inspect_audio_loudness(path: Path) -> Dict[str, float]:
    """Measure mean and max volume in dB using ffmpeg volumedetect filter."""
    if not shutil.which("ffmpeg"):
        return {}
    try:
        from media_tool_identity import MediaTools
        ffmpeg = MediaTools().paths.get("ffmpeg", "ffmpeg")
    except Exception:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-i", str(path),
           "-vn", "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    result = {}
    mean_match = re.search(r"mean_volume:\s*(-?(?:[0-9.]+|inf))\s*dB", res.stderr)
    max_match = re.search(r"max_volume:\s*(-?(?:[0-9.]+|inf))\s*dB", res.stderr)
    if mean_match:
        result["mean_volume"] = float(mean_match.group(1))
    if max_match:
        result["max_volume"] = float(max_match.group(1))
    return result


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
    allow_silent_audio: bool = False,
) -> Dict[str, Any]:
    # Studio saves and export publication share this lock; external writers are
    # also detected by the snapshot checks before verification is published.
    with contract.WRITE_LOCK:
        return _run_validation(repo_root, config_path, artifacts_dir, allow_silent_audio=allow_silent_audio)


def _run_validation(repo_root, config_path, artifacts_dir, allow_silent_audio: bool = False):
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
    global_enabled = preview.get("enabled", False)
    localizations = config.get("localizations", {})
    has_locale_previews = isinstance(localizations, dict) and any(
        isinstance(l_cfg, dict) and "previewVideo" in l_cfg for l_cfg in localizations.values()
    )
    locale_previews = {}
    if has_locale_previews:
        project_locales = config.get("project", {}).get("locales", [])
        all_locales = set(project_locales)
        if isinstance(localizations, dict):
            all_locales.update(localizations.keys())
        for locale in all_locales:
            l_cfg = localizations.get(locale, {}) if isinstance(localizations, dict) else {}
            l_pv = l_cfg.get("previewVideo", {}) if isinstance(l_cfg, dict) else {}
            merged = {**preview, **l_pv}
            if merged.get("enabled", global_enabled):
                locale_previews[locale] = merged

    if locale_previews:
        for locale, lp in locale_previews.items():
            source = lp.get("source")
            if not source or not (repo_root / source).is_file():
                errors.append(f"Enabled previewVideo for {locale} requires an existing real source recording")
            if not (art_dir / f"{locale}/preview/app_preview.mp4").is_file():
                errors.append(f"Missing declared App Preview: {locale}/preview/app_preview.mp4")
            if lp.get("posterRequired") and not (art_dir / f"{locale}/preview/poster.png").is_file():
                errors.append(f"Missing declared poster: {locale}/preview/poster.png")
    elif preview.get("enabled"):
        source = preview.get("source")
        if not source or not (repo_root / source).is_file():
            errors.append("Enabled previewVideo requires an existing real source recording")
        if not (art_dir / "preview/app_preview.mp4").is_file():
            errors.append("Missing declared App Preview: preview/app_preview.mp4")
        if preview.get("posterRequired") and not (art_dir / "preview/poster.png").is_file():
            errors.append("Missing declared poster: preview/poster.png")

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
            allow_alpha = config.get("project", {}).get("allowAlpha", False) or config.get("allowAlpha", False)
            if has_alpha and not allow_alpha:
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
            rel_str = str(rel)
            v_preview = preview
            for loc, lp in locale_previews.items():
                if rel_str.startswith(f"{loc}/preview/"):
                    v_preview = lp
                    break
            allow_silent = (
                allow_silent_audio
                or v_preview.get("allowSilentAudio", False)
                or config.get("allowSilentAudio", False)
            )
            loudness = inspect_audio_loudness(mp4)
            if not allow_silent:
                if not shutil.which("ffmpeg"):
                    raise ValueError("ffmpeg is required to inspect App Preview audio loudness")
                if not loudness or "mean_volume" not in loudness:
                    raise ValueError("ffmpeg failed to detect audio loudness in App Preview")
                mean_vol = loudness.get("mean_volume")
                max_vol = loudness.get("max_volume")
                if (mean_vol is not None and mean_vol < -80.0) or (max_vol is not None and max_vol < -80.0):
                    raise ValueError("App Preview audio track is silent (< -80 dB); audible commentary or soundtrack required")
            if not 14.95 <= duration <= 30.05 or not 0 < fps <= 30:
                raise ValueError("App Preview requires 15-30 seconds and at most 30 fps")
            is_mac = any(x.startswith("mac_") for x in config.get("targets", []))
            portrait = v_preview.get("orientation", "portrait") == "portrait" and not is_mac
            expected_size = (int(v_preview.get("width", 886 if portrait else 1920)),
                             int(v_preview.get("height", 1920 if portrait else (1080 if is_mac else 886))))
            if (width, height) != expected_size:
                raise ValueError(f"App Preview dimensions must be {expected_size}")
            if abs(fps - float(v_preview.get("fps", 30))) > .01:
                raise ValueError("App Preview fps differs from configuration")
            if (v_preview.get("enabled") or locale_previews) and abs(duration - float(v_preview.get("duration", 20))) > .05:
                raise ValueError("App Preview duration differs from configuration")
            v_rec = {"sha256": sha, "type": "video", "size_bytes": size_bytes,
                     "duration": duration, "fps": fps, "width": width, "height": height,
                     "video_codec": video["codec_name"], "audio_codec": audio["codec_name"]}
            if loudness:
                if "mean_volume" in loudness:
                    v_rec["mean_volume_db"] = loudness["mean_volume"]
                if "max_volume" in loudness:
                    v_rec["max_volume_db"] = loudness["max_volume"]
            asset_records[str(rel)] = v_rec
        except Exception as exc:
            errors.append(f"Failed to validate video {rel}: {exc}")

    poster_records = {k: v for k, v in asset_records.items() if k.endswith("preview/poster.png")}
    for poster_path, poster_record in poster_records.items():
        expected_preview_path = poster_path.replace("poster.png", "app_preview.mp4")
        preview_record = asset_records.get(expected_preview_path)
        if not preview_record or preview_record.get("type") != "video":
            errors.append(f"Poster requires a validated App Preview: {poster_path}")
        elif (poster_record["width"], poster_record["height"]) != (preview_record["width"], preview_record["height"]):
            errors.append(f"Poster dimensions must match the validated App Preview: {poster_path}")

    # Return probe facts; the lifecycle core owns immutable validation records.
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

    if errors:
        print("❌ Verification FAILED with issues:")
        for err in errors:
            print(f"   - {err}")
    else:
        print(f"✅ Verification PASSED: {len(asset_records)} assets fully compliant with Apple specifications.")

    return lock_data
