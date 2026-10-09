#!/usr/bin/env python3
"""App Preview video generation engine for App Store Creative v2.0."""

import json
import produce_app_preview
from pathlib import Path
from typing import Any, Dict, Optional


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
    if not preview_cfg.get("enabled", False):
        return None

    src_rel = preview_cfg.get("source")
    if not src_rel:
        raise ValueError("Enabled previewVideo requires a real source recording")

    src_path = repo_root / src_rel
    if not src_path.exists():
        raise FileNotFoundError(f"Source video not found: {src_path}")

    duration = float(preview_cfg.get("duration", 20))
    fps = float(preview_cfg.get("fps", 30))
    orientation = preview_cfg.get("orientation", "portrait")
    targets = config.get("targets", [])
    is_mac = any(t.startswith("mac_") for t in targets)

    # Dimensions for portrait vs landscape:
    # Mac App Store strictly requires 16:9 (1920x1080) for desktop landscape videos
    # iPhone App Previews use 19.5:9 (886x1920 portrait or 1920x886 landscape)
    default_width = 886 if orientation == "portrait" else 1920
    default_height = 1920 if orientation == "portrait" else (1080 if is_mac else 886)

    width = int(preview_cfg.get("width", default_width))
    height = int(preview_cfg.get("height", default_height))

    out_root = output_dir or (repo_root / "artifacts")
    target_out = out_root / "preview" / "app_preview.mp4"
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
                "has_audio": False,  # Will inject silent AAC track automatically
            }
        ],
    }

    print(f"🎬 Producing App Preview video ({width}x{height} @ {fps}fps, {duration}s)...")
    receipt = target_out.with_suffix('.receipt.json')
    frames = target_out.with_suffix('.frames.png')
    result = produce_app_preview.execute(contract, target_out, receipt, frames)
    return {"path": str(target_out), "probe": result["output"]["probe"],
            "receipt_path": str(receipt), "frames_path": str(frames)}
