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


def validate_recording_probe(plan: dict, probe: dict) -> None:
    _validate_recording_probe(plan, probe, native=False)


def validate_native_recording_probe(plan: dict, probe: dict) -> None:
    """ScreenCaptureKit caps cadence; it does not guarantee constant frame rate."""
    _validate_recording_probe(plan, probe, native=True)


def _validate_recording_probe(plan: dict, probe: dict, *, native: bool) -> None:
    """Allow bounded timestamp rounding while rejecting truncated or mismatched takes."""
    import math
    from fractions import Fraction
    try:
        videos = [stream for stream in probe['streams'] if stream.get('codec_type') == 'video']
        if len(videos) != 1:
            raise ValueError('exactly one video stream is required')
        video = videos[0]
        duration = float(probe['format']['duration'])
        rate = float(Fraction(video['avg_frame_rate']))
        if (video['codec_name'] != 'h264' or video['width'] != plan['width']
                or video['height'] != plan['height']):
            raise ValueError('codec or dimensions differ from plan')
        tolerance = max(0.5, 2 / plan['fps'])
        # Native finalization may retain a bounded tail; normalized output remains strict.
        lower = plan['duration'] - tolerance
        upper = plan['duration'] + (10 if native else tolerance)
        if not math.isfinite(duration) or not lower <= duration <= upper:
            raise ValueError('duration differs from plan')
        invalid_rate = (rate <= 0 or rate > plan['fps'] * 1.01) if native else abs(rate - plan['fps']) > plan['fps'] * 0.01
        if not math.isfinite(rate) or invalid_rate:
            raise ValueError('frame rate differs from plan')
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise RecordingContractError('Recording media does not satisfy plan: ' + str(error)) from error


def validate_execution_identity(value):
    """Validate portable recorder facts without treating claims as authentication."""
    import re
    fields = {'compiler', 'recorder_executable_sha256', 'probe_tools', 'environment'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Recording execution identity is missing or invalid')
    def tool(item, name):
        if (not isinstance(item, dict) or set(item) != ({'name', 'version', 'executable_sha256', 'sdk_version', 'target'}
                if name == 'swiftc' else {'name', 'version', 'executable_sha256'})
                or item['name'] != name or not isinstance(item['version'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.+~:-]{1,120}', item['version'])
                or not isinstance(item['executable_sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', item['executable_sha256'])):
            raise ValueError('Recording tool identity is invalid')
    tool(value['compiler'], 'swiftc')
    if (not isinstance(value['compiler']['sdk_version'], str)
            or not re.fullmatch(r'[0-9.]{1,32}', value['compiler']['sdk_version'])
            or value['compiler']['target'] not in ('arm64-apple-macosx15.0', 'x86_64-apple-macosx15.0')):
        raise ValueError('Recording compiler SDK or target identity is invalid')
    if not isinstance(value['probe_tools'], list) or len(value['probe_tools']) != 1:
        raise ValueError('Recording probe identity is invalid')
    tool(value['probe_tools'][0], 'ffprobe')
    if not isinstance(value['recorder_executable_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['recorder_executable_sha256']):
        raise ValueError('Recording executable identity is invalid')
    environment = value['environment']
    if (not isinstance(environment, dict) or set(environment) != {'os', 'os_version', 'architecture'}
            or any(not isinstance(item, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]{1,120}', item)
                   for item in environment.values())):
        raise ValueError('Recording environment identity is invalid')
    return value


def validate_normalization_tools(value):
    """Accept only portable, identified encoder and probe facts."""
    import re
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Recording normalization tools are invalid')
    names = set()
    for item in value:
        if (not isinstance(item, dict) or set(item) != {'name', 'version', 'executable_sha256'}
                or item['name'] not in ('ffmpeg', 'ffprobe') or item['name'] in names
                or not isinstance(item['version'], str)
                or not re.fullmatch(r'[A-Za-z0-9_.+~:-]{1,120}', item['version'])
                or not isinstance(item['executable_sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', item['executable_sha256'])):
            raise ValueError('Recording normalization tool identity is invalid')
        names.add(item['name'])
    return value
