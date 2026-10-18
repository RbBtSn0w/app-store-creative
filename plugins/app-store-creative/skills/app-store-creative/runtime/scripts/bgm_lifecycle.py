"""Apple Loops background-music lifecycle: scan, recommend, and compose.

Implements PRD-002 / ADR-003. Pure Python for CAF header parsing and
recommendation scoring; delegates audio rendering to the Swift CLI binary
(`swift-bgm compose`) which owns AVFoundation/CoreAudio.

The Swift binary is compiled on demand from the adjacent `.swift` source and
cached in the runtime work directory.
"""

from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

APPLE_LOOPS_ROOT = Path("/Library/Audio/Apple Loops")
CAF_INFO_UUID = "29819273b5bf4aefb78d62d1ef90bb2c"
SWIFT_SOURCE = Path(__file__).parent / "swift_bgm_compose.swift"


def scan_catalog(
    library_root: Path = APPLE_LOOPS_ROOT,
) -> dict:
    """Walk the Apple Loops library and extract CAF metadata without decoding audio.

    Returns a catalog dict with provenance, file entries, and per-file errors.
    Per-file parse failures are recorded but do not abort the scan.
    """
    entries: list[dict] = []
    errors: list[dict] = []
    scanned_at = datetime.now(timezone.utc).isoformat()
    if not library_root.is_dir():
        return {
            "schema_version": 1,
            "scanned_at": scanned_at,
            "library_root": str(library_root),
            "total_files": 0,
            "music_loops": 0,
            "sound_effects": 0,
            "available": False,
            "fallback": "synthesize_ambient_bgm",
            "entries": [],
            "errors": [],
        }

    for caf in sorted(library_root.rglob("*.caf")):
        try:
            entry = _parse_caf_header(caf)
            if entry is not None:
                entries.append(entry)
        except Exception as error:  # noqa: BLE001 - per-file failures are non-fatal
            errors.append({"path": str(caf), "error": str(error)})

    sound_effects = [e for e in entries if e.get("pack") == "Final Cut Pro Sound Effects"]
    music_loops = [e for e in entries if e.get("pack") != "Final Cut Pro Sound Effects"]
    return {
        "schema_version": 1,
        "scanned_at": scanned_at,
        "library_root": str(library_root),
        "total_files": len(entries),
        "music_loops": len(music_loops),
        "sound_effects": len(sound_effects),
        "available": True,
        "entries": music_loops,
        "errors": errors,
    }


def _parse_caf_header(path: Path) -> dict | None:
    """Extract metadata, duration, and derived BPM from a CAF file header.

    Returns None if the file lacks the CAF magic or has no parsable metadata.
    """
    tags: dict[str, str] = {}
    sample_rate: float | None = None
    channels: int | None = None
    frames: int | None = None
    with path.open("rb") as handle:
        if handle.read(4) != b"caff":
            return None
        handle.read(4)  # version + flags
        while chunk := handle.read(12):
            if len(chunk) != 12:
                break
            chunk_type, chunk_size = struct.unpack(">4sq", chunk)
            if chunk_size < 0:
                break
            if chunk_type not in (b"uuid", b"info", b"desc", b"pakt"):
                handle.seek(chunk_size, 1)
                continue
            data = handle.read(chunk_size)
            if chunk_type == b"desc" and len(data) >= 28:
                sample_rate = struct.unpack(">d", data[:8])[0]
                channels = struct.unpack(">I", data[24:28])[0]
            elif chunk_type == b"pakt" and len(data) >= 16:
                frames = struct.unpack(">q", data[8:16])[0]
            elif chunk_type == b"info":
                _parse_info_pairs(data[4:], tags)
            elif chunk_type == b"uuid" and data[:16].hex() == CAF_INFO_UUID:
                _parse_info_pairs(data[20:], tags)

    duration = frames / sample_rate if frames is not None and sample_rate else None
    beat_count = tags.get("beat count")
    bpm = None
    if beat_count and duration:
        try:
            bpm = round(float(beat_count) * 60.0 / duration, 2) if float(beat_count) > 0 else None
        except (ValueError, ZeroDivisionError):
            bpm = None

    name = path.stem
    try:
        relative = path.relative_to(library_root) if (library_root := path.parents[-1]) else path.parent
    except ValueError:
        relative = path.parent
    if APPLE_LOOPS_ROOT in path.parents and path.parent != APPLE_LOOPS_ROOT:
        parts = path.relative_to(APPLE_LOOPS_ROOT).parts
        pack = parts[1] if len(parts) > 1 else path.parent.name
    else:
        pack = path.parent.name
    return {
        "path": str(path),
        "name": name,
        "pack": pack,
        "duration": duration,
        "channels": channels,
        "sample_rate": sample_rate,
        "bpm_derived": bpm,
        "tags": tags,
    }


def _parse_info_pairs(data: bytes, target: dict[str, str]) -> None:
    """Parse NUL-separated key-value pairs from CAF info or UUID tag blocks."""
    parts = data.split(b"\0")
    for key, value in zip(parts[::2], parts[1::2]):
        try:
            target[key.decode("utf-8")] = value.decode("utf-8")
        except UnicodeDecodeError:
            continue


def recommend(
    catalog: dict,
    product_context: dict,
    count: int = 3,
) -> dict:
    """Score catalog entries against product context and return a ranked shortlist.

    Scoring is transparent metadata matching (PRD-002): descriptor fit, BPM
    range, genre affinity, duration fit, instrumentation preference. The agent
    (LLM) uses the ranked list plus product context to pick the default.
    """
    if not catalog.get("available"):
        return {"available": False, "fallback": "synthesize_ambient_bgm", "candidates": []}

    genre_hint = str(product_context.get("genre", "")).lower()
    mood_hints = [m.lower() for m in product_context.get("mood", [])]
    tempo_hint = product_context.get("tempo", "moderate")
    target_duration = product_context.get("video_duration_seconds")

    scored: list[tuple[float, dict]] = []
    for entry in catalog.get("entries", []):
        tags = entry.get("tags", {})
        descriptors = [d.strip().lower() for d in tags.get("descriptors", "").split(",")]
        score = 0.0
        mapping: dict[str, str] = {}

        for mood in mood_hints:
            if mood in descriptors:
                score += 3.0
                mapping.setdefault("mood", mood)
        if genre_hint and genre_hint in tags.get("genre", "").lower():
            score += 2.0
            mapping["genre"] = tags["genre"]

        bpm = entry.get("bpm_derived")
        if bpm:
            if tempo_hint == "slow" and 50 <= bpm <= 75:
                score += 2.0
            elif tempo_hint == "moderate" and 70 <= bpm <= 100:
                score += 2.0
            elif tempo_hint == "fast" and bpm > 100:
                score += 2.0
            mapping["tempo"] = f"{bpm} bpm ({tempo_hint} band)"

        duration = entry.get("duration")
        if duration and target_duration:
            wraps = max(0, math.ceil(target_duration / duration) - 1)
            score -= wraps * 0.5
            mapping["loop_fit"] = f"{duration:.1f}s source, {wraps} wrap(s) for {target_duration:.1f}s"

        subcategory = tags.get("subcategory", "")
        instrumentation = product_context.get("instrumentation", [])
        for preferred in instrumentation:
            if preferred.lower() in subcategory.lower():
                score += 1.5
                mapping["instrumentation"] = subcategory

        if score > 0:
            scored.append((score, {**entry, "_score": score, "_mapping": mapping}))

    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    seen_families: set[str] = set()
    candidates: list[dict] = []
    for _, entry in scored:
        family = entry["name"].rsplit(" ", 1)[0]
        if family in seen_families:
            continue
        seen_families.add(family)
        candidates.append({
            "path": entry["path"],
            "name": entry["name"],
            "pack": entry["pack"],
            "score": entry["_score"],
            "duration": entry["duration"],
            "bpm_derived": entry["bpm_derived"],
            "tags": entry["tags"],
            "mapping": entry["_mapping"],
            "license_rationale": (
                "Apple Loops software license permits use in original "
                "soundtracks; no standalone redistribution of the sample."
            ),
        })
        if len(candidates) >= count:
            break

    return {
        "available": True,
        "candidates": candidates,
        "product_context": product_context,
        "note": "Agent selects the default from this ranked shortlist using product context.",
    }


def compose(
    loop_path: Path,
    video_path: Path,
    output_path: Path,
    *,
    fade_in: float = 0.35,
    fade_out_start: float = 18.5,
    fade_out_duration: float = 1.5,
    target_lufs: float = -16.0,
    true_peak_ceiling: float = -1.0,
) -> dict:
    """Compile (if needed) and invoke the Swift CLI, returning the parsed receipt."""
    binary = _ensure_swift_binary()
    command = [
        str(binary),
        "compose",
        "--loop", str(loop_path.resolve()),
        "--video", str(video_path.resolve()),
        "--output", str(output_path.resolve()),
        "--fade-in", str(fade_in),
        "--fade-out-start", str(fade_out_start),
        "--fade-out-duration", str(fade_out_duration),
        "--target-lufs", str(target_lufs),
        "--true-peak-ceiling", str(true_peak_ceiling),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"swift-bgm compose failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


_swift_binary_cache: Path | None = None


def _ensure_swift_binary() -> Path:
    """Compile the Swift source once and cache the binary in a temp directory."""
    global _swift_binary_cache
    if _swift_binary_cache is not None and _swift_binary_cache.is_file():
        return _swift_binary_cache
    work = Path("/tmp") / f"swift-bgm-{uuid.uuid4().hex[:12]}"
    work.mkdir(parents=True, exist_ok=True)
    binary = work / "swift-bgm"
    try:
        subprocess.run(
            [
                "/usr/bin/xcrun", "swiftc", "-O",
                "-parse-as-library",
                "-module-cache-path", str(work / "module-cache"),
                "-module-name", "SwiftBGMCompose",
                str(SWIFT_SOURCE),
                "-o", str(binary),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("swiftc is unavailable; install Xcode Command Line Tools") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Swift compilation failed: {error.stderr}") from error
    _swift_binary_cache = binary
    return binary

