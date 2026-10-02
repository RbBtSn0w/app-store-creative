#!/usr/bin/env python3
"""Compose an App Preview from an explicit JSON contract using ffmpeg."""

import argparse, json, shutil, subprocess, sys
from pathlib import Path


def build_command(contract: dict, output: Path) -> list[str]:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    segments = list(contract.get("segments") or [])
    if not isinstance(segments, list) or not segments: raise ValueError("contract requires non-empty segments")
    width = int(contract["width"]); height = int(contract["height"]); fps = float(contract["fps"]); duration = float(contract["duration"])
    if min(width, height, fps, duration) <= 0: raise ValueError("width, height, fps, and duration must be positive")
    end_card = contract.get("end_card")
    segment_total = sum(float(segment["duration"]) for segment in segments)
    end_duration = float(end_card.get("duration", 0)) if end_card else 0
    if abs(segment_total + end_duration - duration) > 0.01: raise ValueError("segment and end-card durations must equal output duration")
    command = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    for segment in segments:
        command += ["-i", str(Path(segment["path"]))]
    overlay_inputs = []
    for overlay in contract.get("overlays", []):
        if overlay.get("type") == "image":
            overlay_inputs.append(len(segments) + len(overlay_inputs)); command += ["-loop", "1", "-i", str(Path(overlay["path"]))]
    end_input = None
    if end_card:
        end_input = len(segments) + len(overlay_inputs); command += ["-loop", "1", "-i", str(Path(end_card["path"]))]
    filters = []
    concat_inputs = []
    for i, segment in enumerate(segments):
        segment_duration = float(segment.get("duration", duration))
        filters.append(f"[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},trim=duration={segment_duration},setpts=PTS-STARTPTS[v{i}]")
        if segment.get("has_audio", True):
            filters.append(f"[{i}:a:0]atrim=duration={segment_duration},asetpts=PTS-STARTPTS[a{i}]")
        else:
            filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={segment_duration}[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")
    if end_card:
        filters.append(f"[{end_input}:v:0]scale={width}:{height},fps={fps},trim=duration={end_duration},setpts=PTS-STARTPTS[vend]")
        filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={end_duration}[aend]")
        concat_inputs.append("[vend][aend]")
    filters.append("".join(concat_inputs) + f"concat=n={len(concat_inputs)}:v=1:a=1[vbase][a]")
    current = "vbase"
    image_index = 0
    for index, overlay in enumerate(contract.get("overlays", [])):
        start = float(overlay["start"]); end = float(overlay["end"])
        if not 0 <= start < end <= duration: raise ValueError("overlay interval is outside output duration")
        target = f"v{index}o"
        if overlay.get("type") == "text":
            escaped = str(overlay["text"]).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
            filters.append(f"[{current}]drawtext=text='{escaped}':x=(w-text_w)/2:y=h*0.85:enable='between(t,{start},{end})'[{target}]")
        elif overlay.get("type") == "image":
            source_index = overlay_inputs[image_index]; image_index += 1
            filters.append(f"[{source_index}:v:0]format=rgba[overlay{index}];[{current}][overlay{index}]overlay=x={overlay.get('x', 0)}:y={overlay.get('y', 0)}:enable='between(t,{start},{end})'[{target}]")
        else: raise ValueError("overlay type must be text or image")
        current = target
    command += ["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", "[a]", "-t", str(duration),
                "-r", str(fps), "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-ar", "48000", "-movflags", "+faststart", str(output)]
    return command


def validate_output(path: Path, contract: dict) -> dict:
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate", "-of", "json", str(path)],
                           check=True, text=True, capture_output=True)
    payload = json.loads(probe.stdout); streams = payload.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None); audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video or video.get("codec_name") != "h264" or [video.get("width"), video.get("height")] != [contract["width"], contract["height"]]: raise ValueError("output video contract mismatch")
    n, d = (float(v) for v in video["r_frame_rate"].split("/"))
    if abs(n / d - float(contract["fps"])) > 0.01: raise ValueError("output fps mismatch")
    if abs(float(payload["format"]["duration"]) - float(contract["duration"])) > 0.05: raise ValueError("output duration mismatch")
    if not audio or audio.get("codec_name") != "aac": raise ValueError("output AAC audio is required")
    return payload


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("--contract", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--execute", action="store_true")
    args = p.parse_args(argv); contract = json.loads(args.contract.read_text()); command = build_command(contract, args.output)
    if not args.execute: print(json.dumps({"executed": False, "command": command})); return 0
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"): print("ffmpeg and ffprobe are required", file=sys.stderr); return 2
    subprocess.run(command, check=True)
    print(json.dumps({"executed": True, "probe": validate_output(args.output, contract)})); return 0


if __name__ == "__main__": raise SystemExit(main())
