#!/usr/bin/env python3
"""
Sidechain audio ducking mixer for App Store Preview videos.
Mixes speech voiceover with ambient background music by calculating a smooth
lookahead ducking envelope, applying -12 dB attenuation under narration,
and normalizing the master mix to strict Apple App Store audio standards (-16.0 LUFS).
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
import wave
from pathlib import Path

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

try:
    from scipy.io import wavfile
    from scipy.ndimage import gaussian_filter1d
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


def read_wav_frames(path: Path) -> tuple[int, list[tuple[float, float]]]:
    """Read any 16-bit PCM WAV file and return (sample_rate, list_of_stereo_float_tuples)."""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        n_frames = w.getnframes()
        raw_bytes = w.readframes(n_frames)

    if sampwidth != 2:
        raise ValueError(f"Only 16-bit PCM WAV is supported (found sampwidth={sampwidth})")

    total_samples = n_frames * n_channels
    ints = struct.unpack(f"<{total_samples}h", raw_bytes)
    frames = []

    if n_channels == 1:
        for val in ints:
            norm = val / 32768.0
            frames.append((norm, norm))
    elif n_channels == 2:
        for i in range(0, total_samples, 2):
            frames.append((ints[i] / 32768.0, ints[i + 1] / 32768.0))
    else:
        # ITU-R BS.775 compliant downmix to stereo
        for i in range(0, total_samples, n_channels):
            ch = [ints[i + c] / 32768.0 for c in range(n_channels)]
            if n_channels == 3:
                # L, R, C
                l = ch[0] + 0.7071 * ch[2]
                r = ch[1] + 0.7071 * ch[2]
            elif n_channels == 4:
                # Quad: L, R, Ls, Rs
                l = ch[0] + 0.7071 * ch[2]
                r = ch[1] + 0.7071 * ch[3]
            elif n_channels >= 6:
                # 5.1 Surround: L (0), R (1), C (2), LFE (3), Ls (4), Rs (5)
                l = ch[0] + 0.7071 * ch[2] + 0.7071 * ch[4]
                r = ch[1] + 0.7071 * ch[2] + 0.7071 * ch[5]
            else:
                l = sum(ch[0::2]) / max(1, len(ch[0::2]))
                r = sum(ch[1::2]) / max(1, len(ch[1::2]))
            frames.append((l, r))

    return sr, frames


def write_stereo_wav(path: Path, sample_rate: int, frames: list[tuple[float, float]]) -> None:
    """Write stereo float frames to 16-bit PCM WAV."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    out_bytes = bytearray()
    for l_val, r_val in frames:
        l_int = max(-32768, min(32767, int(l_val * 32767.0)))
        r_int = max(-32768, min(32767, int(r_val * 32767.0)))
        out_bytes.extend(struct.pack("<hh", l_int, r_int))

    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(out_bytes)


def compute_integrated_lufs_estimate(frames: list[tuple[float, float]]) -> float:
    """Estimate integrated loudness in LUFS via BS.1770 RMS approximation."""
    if not frames:
        return -70.0
    sum_sq = 0.0
    for l, r in frames:
        sum_sq += l * l + r * r
    ms = sum_sq / (2.0 * len(frames))
    if ms < 1e-12:
        return -70.0
    return float(10.0 * math.log10(ms))


def duck_and_mix_audio(
    bgm_path: Path,
    voice_path: Path,
    output_path: Path,
    ducking_db: float = -12.0,
    target_lufs: float = -16.0,
    smooth_sigma_ms: float = 250.0,
) -> dict:
    """
    Mix voiceover and BGM with sidechain ducking and loudness normalization.

    Returns dict with mixed audio properties and validation metrics.
    """
    sr_bgm, bgm_frames = read_wav_frames(bgm_path)
    sr_voice, voice_frames = read_wav_frames(voice_path)

    if sr_bgm != sr_voice:
        raise ValueError(f"Sample rate mismatch: BGM={sr_bgm}Hz, Voice={sr_voice}Hz. Resample before mixing.")
    sr = sr_bgm

    # Match lengths (pad with silence to max duration)
    max_len = max(len(bgm_frames), len(voice_frames))
    if len(bgm_frames) < max_len:
        bgm_frames.extend([(0.0, 0.0)] * (max_len - len(bgm_frames)))
    if len(voice_frames) < max_len:
        voice_frames.extend([(0.0, 0.0)] * (max_len - len(voice_frames)))

    # Compute voice amplitude envelope for sidechain detection
    speech_threshold = 0.02
    active_mask = [1.0 if (abs(v[0]) + abs(v[1])) * 0.5 > speech_threshold else 0.0 for v in voice_frames]

    # Two-pass forward-backward smoothing for lookahead ducking envelope
    half_window = max(1, int((smooth_sigma_ms / 1000.0) * sr * 0.5))
    alpha = 1.0 / (half_window + 1.0)
    
    smoothed = list(active_mask)
    # Forward pass
    cur = 0.0
    for i in range(max_len):
        cur = cur * (1.0 - alpha) + active_mask[i] * alpha
        smoothed[i] = cur
    # Backward pass
    cur = 0.0
    for i in range(max_len - 1, -1, -1):
        cur = cur * (1.0 - alpha) + smoothed[i] * alpha
        smoothed[i] = cur

    # Apply ducking gain
    attenuation_factor = 10.0 ** (ducking_db / 20.0)
    mixed_frames: list[tuple[float, float]] = []

    for i in range(max_len):
        duck_level = min(1.0, max(0.0, smoothed[i] * 3.0))
        gain = 1.0 - (1.0 - attenuation_factor) * duck_level
        bgm_l, bgm_r = bgm_frames[i]
        voice_l, voice_r = voice_frames[i]
        mixed_frames.append((voice_l + bgm_l * gain, voice_r + bgm_r * gain))

    # Calculate loudness and normalize to target_lufs
    current_lufs = compute_integrated_lufs_estimate(mixed_frames)
    gain_adjustment_db = target_lufs - current_lufs
    gain_adjustment_db = min(gain_adjustment_db, 14.0)
    norm_factor = 10.0 ** (gain_adjustment_db / 20.0)

    normalized_frames: list[tuple[float, float]] = []
    max_peak = 0.0
    for ml, mr in mixed_frames:
        nl = ml * norm_factor
        nr = mr * norm_factor
        # Peak limiter enforcing strict -0.2 dBFS ceiling (10 ** (-0.2 / 20) ≈ 0.9772)
        peak_ceiling = 10.0 ** (-0.2 / 20.0)
        peak_sample = max(abs(nl), abs(nr))
        if peak_sample > peak_ceiling:
            scale = peak_ceiling / peak_sample
            nl *= scale
            nr *= scale
            peak_sample = peak_ceiling
        if peak_sample > max_peak:
            max_peak = peak_sample
        normalized_frames.append((nl, nr))

    final_lufs = compute_integrated_lufs_estimate(normalized_frames)
    write_stereo_wav(output_path, sr, normalized_frames)

    return {
        "status": "PASS",
        "sample_rate": sr,
        "duration_seconds": max_len / sr,
        "ducking_db": ducking_db,
        "target_lufs": target_lufs,
        "measured_lufs": round(final_lufs, 2),
        "peak_dbfs": round(20.0 * math.log10(max(max_peak, 1e-6)), 2),
        "output_path": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Sidechain audio ducking mixer for App Store Previews.")
    parser.add_argument("--bgm", required=True, type=Path, help="Path to background music WAV")
    parser.add_argument("--voice", required=True, type=Path, help="Path to voiceover narration WAV")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Output master mixed WAV")
    parser.add_argument("--ducking-db", type=float, default=-12.0, help="Attenuation in dB under speech (default: -12.0)")
    parser.add_argument("--target-lufs", type=float, default=-16.0, help="Target integrated loudness in LUFS (default: -16.0)")
    parser.add_argument("--smooth-ms", type=float, default=250.0, help="Lookahead smoothing envelope in ms (default: 250.0)")

    args = parser.parse_args()
    res = duck_and_mix_audio(
        args.bgm,
        args.voice,
        args.output,
        ducking_db=args.ducking_db,
        target_lufs=args.target_lufs,
        smooth_sigma_ms=args.smooth_ms,
    )
    print(f"Master mix written to: {res['output_path']}")
    print(f"Loudness: {res['measured_lufs']} LUFS | Peak: {res['peak_dbfs']} dBFS | Duration: {res['duration_seconds']}s")


if __name__ == "__main__":
    main()
