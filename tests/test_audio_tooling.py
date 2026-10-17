"""Unit tests for TASK-203: Audio Tooling & Capture Templates (Issue #48)."""
from pathlib import Path
import math
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))

from synthesize_ambient_bgm import generate_ambient_bgm
from audio_ducking_mixer import duck_and_mix_audio, read_wav_frames, write_stereo_wav


class AudioToolingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_synthesize_ambient_bgm_execution(self):
        output_wav = self.root / "test_bgm.wav"
        generate_ambient_bgm(output_wav, duration=2.0, sample_rate=48000, vocal_notch=True)
        self.assertTrue(output_wav.is_file())
        self.assertGreater(output_wav.stat().st_size, 1000)

        sr, frames = read_wav_frames(output_wav)
        self.assertEqual(sr, 48000)
        # 2.0s @ 48000 = 96000 stereo frames
        self.assertEqual(len(frames), 96000)

    def test_synthesize_ambient_bgm_cli(self):
        output_wav = self.root / "cli_bgm.wav"
        script = Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts/synthesize_ambient_bgm.py"
        subprocess.run(
            [sys.executable, str(script), "--output", str(output_wav), "--duration", "1.5", "--sample-rate", "48000"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertTrue(output_wav.is_file())
        sr, frames = read_wav_frames(output_wav)
        self.assertEqual(sr, 48000)
        self.assertEqual(len(frames), 72000)

    def test_audio_ducking_mixer(self):
        bgm_wav = self.root / "bgm.wav"
        voice_wav = self.root / "voice.wav"
        mixed_wav = self.root / "master.wav"

        # Generate 2.0s BGM
        generate_ambient_bgm(bgm_wav, duration=2.0, sample_rate=48000)

        # Generate 2.0s synthetic voice with speech in the middle (0.5s to 1.5s)
        sr, bgm_frames = read_wav_frames(bgm_wav)
        voice_frames = []
        for i in range(len(bgm_frames)):
            if 24000 <= i < 72000:
                tone = 0.5 * math.sin(2.0 * math.pi * 300.0 * (i / 48000.0))
                voice_frames.append((tone, tone))
            else:
                voice_frames.append((0.0, 0.0))
        write_stereo_wav(voice_wav, 48000, voice_frames)

        res = duck_and_mix_audio(
            bgm_wav,
            voice_wav,
            mixed_wav,
            ducking_db=-12.0,
            target_lufs=-16.0,
            smooth_sigma_ms=100.0,
        )

        self.assertEqual(res["status"], "PASS")
        self.assertTrue(mixed_wav.is_file())
        self.assertEqual(res["sample_rate"], 48000)
        self.assertEqual(res["duration_seconds"], 2.0)
        # Measured loudness should be in the realm of target (-16 +/- 3 dB)
        self.assertAlmostEqual(res["measured_lufs"], -16.0, delta=3.0)

    def test_audio_ducking_mixer_cli(self):
        bgm_wav = self.root / "cli_bgm.wav"
        voice_wav = self.root / "cli_voice.wav"
        mixed_wav = self.root / "cli_master.wav"

        generate_ambient_bgm(bgm_wav, duration=1.0, sample_rate=48000)
        generate_ambient_bgm(voice_wav, duration=1.0, sample_rate=48000)

        script = Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts/audio_ducking_mixer.py"
        subprocess.run(
            [
                sys.executable, str(script),
                "--bgm", str(bgm_wav),
                "--voice", str(voice_wav),
                "-o", str(mixed_wav),
                "--ducking-db", "-12.0",
                "--target-lufs", "-16.0",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertTrue(mixed_wav.is_file())
        sr, frames = read_wav_frames(mixed_wav)
        self.assertEqual(sr, 48000)
        self.assertEqual(len(frames), 48000)


if __name__ == "__main__":
    unittest.main()
