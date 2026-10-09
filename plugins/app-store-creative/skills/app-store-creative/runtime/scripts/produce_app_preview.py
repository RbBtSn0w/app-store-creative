#!/usr/bin/env python3
"""Compose an App Preview from an explicit JSON contract using ffmpeg."""

import argparse, hashlib, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path


def overlay_coordinate(value, bound, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not -bound <= value <= bound or not math.isfinite(value)):
        raise ValueError('Overlay coordinate ' + name + ' must be a finite canvas position')
    return value


def build_command(contract: dict, output: Path, tools=None) -> list[str]:
    ffmpeg = tools.paths["ffmpeg"] if tools is not None else shutil.which("ffmpeg") or "ffmpeg"
    segments = contract.get("segments") or []
    if not isinstance(segments, list) or not segments: raise ValueError("contract requires non-empty segments")
    width = int(contract["width"]); height = int(contract["height"]); fps = float(contract["fps"]); duration = float(contract["duration"])
    if not all(math.isfinite(v) and v > 0 for v in (width, height, fps, duration)): raise ValueError("width, height, fps, and duration must be positive")
    end_card = contract.get("end_card")
    for segment in segments:
        start = float(segment.get("start", 0)); length = float(segment["duration"])
        if not math.isfinite(start) or start < 0 or not math.isfinite(length) or length <= 0:
            raise ValueError("segment start must be finite and nonnegative; duration must be finite and positive")
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
        start = float(segment.get("start", 0))
        filters.append(f"[{i}:v:0]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},trim=start={start}:duration={segment_duration},setpts=PTS-STARTPTS[v{i}]")
        if segment.get("has_audio", True):
            filters.append(f"[{i}:a:0]atrim=start={start}:duration={segment_duration},asetpts=PTS-STARTPTS[a{i}]")
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
            x = overlay_coordinate(overlay.get('x', 0), width, 'x')
            y = overlay_coordinate(overlay.get('y', 0), height, 'y')
            filters.append(f"[{source_index}:v:0]format=rgba[overlay{index}];[{current}][overlay{index}]overlay=x={x}:y={y}:enable='between(t,{start},{end})'[{target}]")
        else: raise ValueError("overlay type must be text or image")
        current = target
    command += ["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", "[a]", "-t", str(duration),
                "-r", str(fps), "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-ar", "48000", "-movflags", "+faststart", str(output)]
    return command


def validate_output(path: Path, contract: dict, tools=None) -> dict:
    probe = subprocess.run([tools.paths["ffprobe"] if tools is not None else "ffprobe", "-v", "error", "-show_entries",
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


def digest(path: Path) -> str:
    with path.open("rb") as source:
        result = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
        return result.hexdigest()


def probe_media(path: Path, tools=None) -> dict:
    result = subprocess.run([tools.paths["ffprobe"] if tools is not None else "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def preflight_sources(contract: dict, tools=None) -> list[dict]:
    sources = []
    for segment in contract["segments"]:
        path = Path(segment["path"]).resolve()
        probe = probe_media(path, tools)
        if not any(s.get("codec_type") == "video" for s in probe.get("streams", [])):
            raise ValueError(f"source has no video: {path}")
        if float(segment.get("start", 0)) + float(segment["duration"]) > float(probe["format"]["duration"]) + 0.01:
            raise ValueError(f"segment exceeds source duration: {path}")
        if segment.get("has_audio", True) and not any(s.get("codec_type") == "audio" for s in probe.get("streams", [])):
            raise ValueError(f"source has no audio; explicitly set has_audio=false: {path}")
        sources.append({"path": str(path), "sha256": digest(path), "probe": probe})
    for image in [*contract.get("overlays", []), contract.get("end_card") or {}]:
        if image.get("path"):
            path = Path(image["path"]).resolve()
            sources.append({"path": str(path), "sha256": digest(path)})
    return sources


def execute(contract: dict, output: Path, receipt: Path, snapshot: Path) -> dict:
    output, receipt, snapshot = (path.parent.resolve() / path.name for path in (output, receipt, snapshot))
    command = build_command(contract, output)
    for path in (output, receipt, snapshot):
        if path.exists(): raise ValueError(f"refusing to overwrite existing artifact: {path}")
    if len({p.resolve() for p in (output, receipt, snapshot)}) != 3:
        raise ValueError("output, receipt, and snapshot must be distinct")
    from media_tool_identity import MediaTools
    tools = MediaTools()
    command = build_command(contract, output, tools)
    filters = subprocess.run([tools.paths["ffmpeg"], "-hide_banner", "-filters"], check=True, capture_output=True, text=True).stdout
    if any(o.get("type") == "text" for o in contract.get("overlays", [])) and "drawtext" not in filters:
        raise ValueError("this ffmpeg build lacks drawtext; use an image overlay or a build with drawtext")
    sources = preflight_sources(contract, tools)
    for path in (output, receipt, snapshot): path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        encoded = Path(scratch) / output.name
        actual_command = build_command(contract, encoded, tools)
        subprocess.run(actual_command, check=True, capture_output=True)
        probe = validate_output(encoded, contract, tools)
        image = Path(scratch) / "acceptance.png"
        # Six evenly spaced real frames; editorial review remains a human decision.
        snapshot_command = [tools.paths["ffmpeg"], "-hide_banner", "-nostdin", "-y", "-i", str(encoded),
                            "-vf", f"fps=6/{float(contract['duration'])},scale=480:-1,tile=3x2",
                            "-frames:v", "1", str(image)]
        subprocess.run(snapshot_command, check=True, capture_output=True)
        if any(digest(Path(s["path"])) != s["sha256"] for s in sources):
            raise ValueError("source changed while producing preview")
        tools.verify()
        result = {"schema_version": 1, "tools": tools.evidence, "producer": "app-store-creative", "kind": "preview-production",
                  "contract_sha256": hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest(),
                  "sources": sources, "contract": contract, "segments": contract["segments"],
                  "command": command, "execution_command": actual_command,
                  "output": {"path": str(output.resolve()), "sha256": digest(encoded), "probe": probe},
                  "acceptance_snapshot": {"path": str(snapshot.resolve()), "sha256": digest(image)},
                  "snapshot_command": snapshot_command, "uploaded": False}
        from safe_staging import staged_file
        for source, destination in ((image, snapshot), (encoded, output)):
            with staged_file(destination.parent) as staged:
                with source.open('rb') as stream:
                    shutil.copyfileobj(stream, staged.stream)
                staged.sync()
                staged.publish(destination)
        with staged_file(receipt.parent) as staged:
            staged.stream.write((json.dumps(result, indent=2) + "\n").encode('utf-8'))
            staged.sync()
            staged.publish(receipt)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("--contract", type=Path, required=True); p.add_argument("--output", type=Path, required=True); p.add_argument("--execute", action="store_true")
    p.add_argument("--receipt", type=Path); p.add_argument("--snapshot", type=Path)
    args = p.parse_args(argv)
    try:
        contract = json.loads(args.contract.read_text())
        for item in [*contract.get("segments", []), *contract.get("overlays", []), contract.get("end_card") or {}]:
            if item.get("path"):
                item["path"] = str((args.contract.resolve().parent / item["path"]).resolve())
        command = build_command(contract, args.output)
        if not args.execute: print(json.dumps({"executed": False, "command": command})); return 0
        result = execute(contract, args.output, args.receipt or args.output.with_suffix(".receipt.json"),
                         args.snapshot or args.output.with_suffix(".acceptance.png"))
        print(json.dumps({"executed": True, "output": result["output"], "acceptance_snapshot": result["acceptance_snapshot"]})); return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr); return 2


if __name__ == "__main__": raise SystemExit(main())
