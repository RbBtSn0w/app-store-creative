#!/usr/bin/env python3
"""
Synthesize an ambient electronic BGM track for App Store Preview videos.
Generates warm, wide stereo pad chords tailored for Apple Keynote / developer-tool previews,
with gentle vocal-band notch filtering (1.2kHz-3.5kHz, applied when SciPy is available)
to leave headroom for narration. Pure-stdlib mode synthesizes pad chord voices directly.
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
    from scipy.signal import butter, sosfiltfilt
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


def midi_to_freq(m: float) -> float:
    return 440.0 * (2.0 ** ((m - 69.0) / 12.0))


def synthesize_bgm_numpy(duration: float, sample_rate: int = 48000, vocal_notch: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Synthesize high-fidelity ambient stereo BGM using numpy and scipy."""
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, endpoint=False)

    chord_progression = [
        ([53, 57, 60, 64, 67], 6.0),  # Fmaj9 (F3, A3, C4, E4, G4)
        ([45, 52, 55, 60, 64], 6.0),  # Am7/E (A2, E3, G3, C4, E4)
        ([46, 53, 58, 62, 65], 6.0),  # Bbmaj7 (Bb2, F3, Bb3, D4, F4)
        ([48, 55, 58, 62, 67], 6.0),  # C9sus4 (C3, G3, Bb3, D4, G4)
    ]

    left_channel = np.zeros(n_samples, dtype=np.float64)
    right_channel = np.zeros(n_samples, dtype=np.float64)

    detunes = [-0.003, -0.001, 0.001, 0.003]

    cur_time = 0.0
    while cur_time < duration:
        for notes, chord_dur in chord_progression:
            if cur_time >= duration:
                break
            seg_start = int(cur_time * sample_rate)
            seg_len = min(int(chord_dur * sample_rate), n_samples - seg_start)
            if seg_len <= 0:
                break

            lt = np.linspace(0, seg_len / sample_rate, seg_len, endpoint=False)
            env = np.ones(seg_len, dtype=np.float64)
            att = min(int(0.5 * sample_rate), seg_len // 3)
            rel = min(int(0.7 * sample_rate), seg_len // 3)
            if att > 0:
                env[:att] = 0.5 * (1.0 - np.cos(np.pi * np.linspace(0, 1, att)))
            if rel > 0:
                env[-rel:] = 0.5 * (1.0 + np.cos(np.pi * np.linspace(0, 1, rel)))

            chord_left = np.zeros(seg_len, dtype=np.float64)
            chord_right = np.zeros(seg_len, dtype=np.float64)

            for midinote in notes:
                base_f = midi_to_freq(midinote)
                for idx, d in enumerate(detunes):
                    f = base_f * (1.0 + d)
                    phase = 2.0 * np.pi * f * lt + (idx * 0.7)
                    osc = (
                        0.65 * np.sin(phase)
                        + 0.22 * np.sin(2.0 * phase + 0.3)
                        + 0.08 * np.sin(3.0 * phase)
                    )
                    lfo = 0.5 + 0.5 * np.sin(2.0 * np.pi * (0.2 + 0.05 * idx) * lt)
                    if idx % 2 == 0:
                        chord_left += osc * (0.6 + 0.3 * lfo)
                        chord_right += osc * (0.4 - 0.15 * lfo)
                    else:
                        chord_left += osc * (0.4 - 0.15 * lfo)
                        chord_right += osc * (0.6 + 0.3 * lfo)

            chord_left *= env * 0.12
            chord_right *= env * 0.12

            left_channel[seg_start:seg_start + seg_len] += chord_left
            right_channel[seg_start:seg_start + seg_len] += chord_right

            cur_time += chord_dur

    # Sub-bass warmth
    bass_phase = 2.0 * np.pi * 43.65 * t
    bass = 0.18 * (np.sin(bass_phase) + 0.25 * np.sin(2.0 * bass_phase))
    left_channel += bass
    right_channel += bass

    # Master envelope
    master_att = min(int(0.5 * sample_rate), n_samples // 4)
    master_rel = min(int(1.2 * sample_rate), n_samples // 4)
    if master_att > 0:
        left_channel[:master_att] *= 0.5 * (1.0 - np.cos(np.pi * np.linspace(0, 1, master_att)))
        right_channel[:master_att] *= 0.5 * (1.0 - np.cos(np.pi * np.linspace(0, 1, master_att)))
    if master_rel > 0:
        left_channel[-master_rel:] *= 0.5 * (1.0 + np.cos(np.pi * np.linspace(0, 1, master_rel)))
        right_channel[-master_rel:] *= 0.5 * (1.0 + np.cos(np.pi * np.linspace(0, 1, master_rel)))

    if HAVE_SCIPY and vocal_notch:
        sos_lp = butter(4, 8500.0 / (sample_rate * 0.5), btype="low", output="sos")
        left_channel = sosfiltfilt(sos_lp, left_channel)
        right_channel = sosfiltfilt(sos_lp, right_channel)

        sos_notch = butter(2, [1200.0 / (sample_rate * 0.5), 3500.0 / (sample_rate * 0.5)], btype="bandstop", output="sos")
        left_channel = 0.7 * sosfiltfilt(sos_notch, left_channel) + 0.3 * left_channel
        right_channel = 0.7 * sosfiltfilt(sos_notch, right_channel) + 0.3 * right_channel

    max_peak = max(np.max(np.abs(left_channel)), np.max(np.abs(right_channel)), 1e-6)
    target_peak = 10.0 ** (-3.0 / 20.0)
    scale = target_peak / max_peak
    left_channel *= scale
    right_channel *= scale

    return left_channel, right_channel


def synthesize_bgm_pure_python(duration: float, sample_rate: int = 48000) -> tuple[list[float], list[float]]:
    """Pure Python fallback sine pad synthesis when numpy is absent."""
    n_samples = int(sample_rate * duration)
    left = [0.0] * n_samples
    right = [0.0] * n_samples

    chord_notes = [174.61, 220.00, 261.63, 329.63]  # F3 chord (F, A, C, E)
    for freq in chord_notes:
        phase_step = 2.0 * math.pi * freq / sample_rate
        cur_phase = 0.0
        for i in range(n_samples):
            val = 0.18 * math.sin(cur_phase)
            left[i] += val
            right[i] += val
            cur_phase += phase_step

    # Master envelope
    fade_len = min(int(0.5 * sample_rate), n_samples // 4)
    if fade_len > 0:
        for i in range(fade_len):
            fade = float(i) / fade_len
            left[i] *= fade
            right[i] *= fade
            left[-(i + 1)] *= fade
            right[-(i + 1)] *= fade

    return left, right


def write_stereo_wav(path: Path, sample_rate: int, left: list[float], right: list[float]) -> None:
    """Write stereo float arrays to 16-bit PCM WAV using standard library wave module."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = len(left)
    frames = bytearray()
    for i in range(n_samples):
        l_int = max(-32768, min(32767, int(left[i] * 32767.0)))
        r_int = max(-32768, min(32767, int(right[i] * 32767.0)))
        frames.extend(struct.pack("<hh", l_int, r_int))

    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(frames)


def generate_ambient_bgm(output_path: Path, duration: float = 24.0, sample_rate: int = 48000, vocal_notch: bool = True) -> Path:
    """Generate and write an ambient electronic BGM track."""
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if HAVE_NUMPY:
        left, right = synthesize_bgm_numpy(duration, sample_rate, vocal_notch)
        if HAVE_SCIPY:
            audio_data = np.column_stack((left, right))
            int_data = (audio_data * 32767.0).astype("int16")
            wavfile.write(str(output_path), sample_rate, int_data)
        else:
            write_stereo_wav(output_path, sample_rate, left.tolist(), right.tolist())
    else:
        left, right = synthesize_bgm_pure_python(duration, sample_rate)
        write_stereo_wav(output_path, sample_rate, left, right)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Synthesize Keynote-style ambient BGM for App Store Previews.")
    parser.add_argument("--output", "-o", required=True, type=Path, help="Output WAV file path")
    parser.add_argument("--duration", "-d", type=float, default=24.0, help="Duration in seconds (default: 24.0)")
    parser.add_argument("--sample-rate", "-r", type=int, default=48000, help="Sample rate in Hz (default: 48000)")
    parser.add_argument("--no-vocal-notch", action="store_true", help="Disable vocal clarity notch filter")

    args = parser.parse_args()
    out = generate_ambient_bgm(args.output, args.duration, args.sample_rate, not args.no_vocal_notch)
    print(f"Synthesized ambient BGM: {out} ({args.duration}s @ {args.sample_rate}Hz stereo)")


if __name__ == "__main__":
    main()
