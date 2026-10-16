"""Unit tests for TASK-203: Native macOS Capabilities & 3-Tier Neural TTS (Issue #38)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))

import recording_adapters as adapters
import record_app_window


class AudioAndTTSCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.output_mov = self.root / "take.mov"

    def test_macos_recording_plan_capture_audio_default_and_overrides(self):
        # Default is capture_audio=True
        plan_default = adapters.macos_recording_plan(
            bundle_id="com.example.app",
            window_id=10,
            output=self.output_mov,
            duration=15,
        )
        self.assertIn("capture_audio", plan_default)
        self.assertTrue(plan_default["capture_audio"])

        # Explicit capture_audio=False
        plan_no_audio = adapters.macos_recording_plan(
            bundle_id="com.example.app",
            window_id=10,
            output=self.output_mov,
            duration=15,
            capture_audio=False,
        )
        self.assertIn("capture_audio", plan_no_audio)
        self.assertFalse(plan_no_audio["capture_audio"])

        # Invalid type rejected
        with self.assertRaises(adapters.RecordingContractError):
            adapters.macos_recording_plan(
                bundle_id="com.example.app",
                window_id=10,
                output=self.output_mov,
                duration=15,
                capture_audio="yes",  # not a bool
            )

    def test_record_app_window_cli_args_for_capture_audio(self):
        output_path = self.root / "window.mov"

        # Test default
        with mock.patch("builtins.print") as mock_print:
            code = record_app_window.main([
                "--bundle-id", "com.example.app",
                "--window-id", "10",
                "--output", str(output_path),
                "--duration", "15",
            ])
            self.assertEqual(code, 0)
            args, _ = mock_print.call_args
            printed = json.loads(args[0])
            self.assertTrue(printed["plan"]["capture_audio"])

        # Test --no-capture-audio
        with mock.patch("builtins.print") as mock_print:
            code = record_app_window.main([
                "--bundle-id", "com.example.app",
                "--window-id", "10",
                "--output", str(output_path),
                "--duration", "15",
                "--no-capture-audio",
            ])
            self.assertEqual(code, 0)
            args, _ = mock_print.call_args
            printed = json.loads(args[0])
            self.assertFalse(printed["plan"]["capture_audio"])

    def test_macos_speech_synthesizer_script_exists_and_runnable(self):
        script = Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts/macos_speech_synthesizer.swift"
        self.assertTrue(script.is_file(), "macos_speech_synthesizer.swift must exist")

        # Test --help flag with swift
        res = subprocess.run(["swift", str(script), "--help"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Usage: macos_speech_synthesizer", res.stdout)
        self.assertIn("--list-voices", res.stdout)
        self.assertIn("--output", res.stdout)


if __name__ == "__main__":
    unittest.main()
