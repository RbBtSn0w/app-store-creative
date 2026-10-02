#!/usr/bin/env python3
"""Safe command builders for platform recording adapters; never records by itself."""

from __future__ import annotations

import shlex
from pathlib import Path


class RecordingContractError(ValueError): pass


def ios_simulator_command(udid: str, output: Path, *, codec: str = "hevc") -> list[str]:
    if not udid or any(c.isspace() for c in udid): raise RecordingContractError("invalid simulator UDID")
    if output.suffix.lower() not in {".mov", ".mp4"}: raise RecordingContractError("video output must be .mov or .mp4")
    if codec not in {"h264", "hevc"}: raise RecordingContractError("unsupported codec")
    return ["xcrun", "simctl", "io", udid, "recordVideo", "--codec", codec, str(output)]


def macos_screencapturekit_contract(*, bundle_id: str, output: Path, include_cursor: bool = False,
                                    capture_scope: str = "window") -> dict:
    if capture_scope != "window": raise RecordingContractError("desktop fallback is forbidden; capture_scope must be window")
    if include_cursor: raise RecordingContractError("cursor capture is forbidden for App Store previews")
    if not bundle_id: raise RecordingContractError("bundle_id is required")
    if output.suffix.lower() not in {".mov", ".mp4"}: raise RecordingContractError("video output must be .mov or .mp4")
    return {"adapter": "ScreenCaptureKit", "bundle_id": bundle_id, "capture_scope": "window",
            "include_cursor": False, "output": str(output)}


def shell_preview(command: list[str]) -> str:
    return shlex.join(command)


def macos_recording_plan(*, bundle_id: str, window_id: int, output: Path,
                         duration: float, width: int = 1920, height: int = 1080,
                         fps: int = 30) -> dict:
    import math
    plan = macos_screencapturekit_contract(bundle_id=bundle_id, output=output)
    if output.suffix.lower() != ".mov":
        raise RecordingContractError("native recording output must be .mov")
    if not isinstance(window_id, int) or isinstance(window_id, bool) or window_id <= 0:
        raise RecordingContractError("an explicit positive window ID is required")
    if not math.isfinite(duration) or not 0 < duration <= 3600:
        raise RecordingContractError("duration must be finite and between 0 and 3600 seconds")
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in (width, height, fps)):
        raise RecordingContractError("width, height, and fps must be positive integers")
    if width > 7680 or height > 7680 or fps > 60:
        raise RecordingContractError("recording dimensions or fps exceed supported bounds")
    plan.update(window_id=window_id, duration=duration, width=width, height=height, fps=fps)
    return plan
