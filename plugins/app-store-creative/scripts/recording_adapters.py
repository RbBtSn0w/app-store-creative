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
