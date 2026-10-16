#!/usr/bin/env python3
"""App Preview video generation engine for App Store Creative v2.0."""

import json
import shutil
import subprocess
import sys
import produce_app_preview
from pathlib import Path
from typing import Any, Dict, Optional


def probe_video(path: Path) -> Dict[str, Any]:
    """Inspect video file streams and format via ffprobe."""
    try:
        from media_tool_identity import MediaTools
        ffprobe = MediaTools().paths.get("ffprobe", "ffprobe")
    except Exception:
        import shutil
        ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def produce_preview_from_config(
    repo_root: Path,
    config_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Produce an Apple-compliant App Preview video from creative.config.json."""
    cfg_file = config_path or (repo_root / "creative.config.json")
    if not cfg_file.exists():
        return None

    config = json.loads(cfg_file.read_text())
    preview_cfg = config.get("previewVideo", {})
    global_enabled = preview_cfg.get("enabled", False)
    localizations = config.get("localizations", {})
    locale_previews = {}
    if isinstance(localizations, dict):
        for locale, l_cfg in localizations.items():
            if isinstance(l_cfg, dict) and "previewVideo" in l_cfg:
                merged = {**preview_cfg, **l_cfg["previewVideo"]}
                if merged.get("enabled", global_enabled):
                    locale_previews[locale] = merged

    if not global_enabled and not locale_previews:
        return None

    out_root = output_dir or (repo_root / "artifacts")
    targets = config.get("targets", [])
    is_mac = any(t.startswith("mac_") for t in targets)

    def _produce_single(p_cfg: Dict[str, Any], target_out: Path, logical_path: str) -> Dict[str, Any]:
        src_rel = p_cfg.get("source")
        if not src_rel:
            raise ValueError("Enabled previewVideo requires a real source recording")

        src_path = repo_root / src_rel
        if not src_path.exists():
            raise FileNotFoundError(f"Source video not found: {src_path}")

        has_audio = False
        if shutil.which("ffprobe"):
            probe = probe_video(src_path)
            streams = probe.get("streams", [])
            has_audio = any(s.get("codec_type") == "audio" for s in streams)

        audio_src_rel = p_cfg.get("audioSource") or p_cfg.get("audio_source")
        audio_src_path = (repo_root / audio_src_rel).resolve() if audio_src_rel else None
        if audio_src_path and not audio_src_path.exists():
            raise FileNotFoundError(f"Audio source not found: {audio_src_path}")

        duration = float(p_cfg.get("duration", 20))
        fps = float(p_cfg.get("fps", 30))
        orientation = p_cfg.get("orientation", "portrait")

        default_width = 886 if orientation == "portrait" else 1920
        default_height = 1920 if orientation == "portrait" else (1080 if is_mac else 886)

        width = int(p_cfg.get("width", default_width))
        height = int(p_cfg.get("height", default_height))

        target_out.parent.mkdir(parents=True, exist_ok=True)

        contract = {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
            "segments": [
                {
                    "path": str(src_path.resolve()),
                    "duration": duration,
                    "has_audio": has_audio,
                }
            ],
        }
        if audio_src_path:
            contract["audio_source"] = str(audio_src_path)

        print(f"🎬 Producing App Preview video ({width}x{height} @ {fps}fps, {duration}s) -> {logical_path}...", file=sys.stderr)
        receipt = target_out.with_suffix('.receipt.json')
        frames = target_out.with_suffix('.frames.png')
        try:
            result = produce_app_preview.execute(contract, target_out, receipt, frames)
        except subprocess.CalledProcessError as error:
            diagnostic = error.stderr or error.stdout or 'No encoder diagnostic output'
            if isinstance(diagnostic, bytes):
                diagnostic = diagnostic.decode('utf-8', errors='replace')
            raise RuntimeError(f'App Preview encoder failed ({error.returncode}): {diagnostic[-4096:]}') from error
        return {
            "path": str(target_out),
            "probe": result["output"]["probe"],
            "receipt_path": str(receipt),
            "frames_path": str(frames),
            "logical_path": logical_path,
        }

    if locale_previews:
        videos = {}
        for locale, lp in locale_previews.items():
            logical_path = f"{locale}/preview/app_preview.mp4"
            target_out = out_root / locale / "preview" / "app_preview.mp4"
            videos[locale] = _produce_single(lp, target_out, logical_path)
        first = next(iter(videos.values()))
        return {
            "path": first["path"],
            "probe": first["probe"],
            "receipt_path": first["receipt_path"],
            "frames_path": first["frames_path"],
            "logical_path": first["logical_path"],
            "videos": videos,
        }
    elif global_enabled:
        logical_path = "preview/app_preview.mp4"
        target_out = out_root / "preview" / "app_preview.mp4"
        return _produce_single(preview_cfg, target_out, logical_path)
    return None
