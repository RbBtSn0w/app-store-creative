"""Observable media regression; optional when FFmpeg is unavailable."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "plugins/app-store-creative/scripts/produce_app_preview.py"
SPEC = importlib.util.spec_from_file_location("timeline_producer", SCRIPT)
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is not installed")
class PreviewProductionTests(unittest.TestCase):
    def test_source_interval_changes_visible_pixels_and_writes_bound_receipt(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch); source = root / "take.mov"; output = root / "preview.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=red:s=64x64:r=30:d=1",
                            "-f", "lavfi", "-i", "color=blue:s=64x64:r=30:d=1", "-filter_complex",
                            "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", str(source)],
                           check=True, capture_output=True)
            contract = {"width": 64, "height": 64, "fps": 30, "duration": 1,
                        "segments": [{"path": str(source), "start": 1, "duration": 1, "has_audio": False}]}
            receipt = root / "preview.receipt.json"; snapshot = root / "acceptance.png"
            result = producer.execute(contract, output, receipt, snapshot)
            pixel = subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-frames:v", "1",
                                    "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                                   check=True, capture_output=True).stdout
            self.assertGreater(pixel[2], pixel[0] + 100)
            self.assertEqual(json.loads(receipt.read_text()), result)
            for asset in result["sources"] + [result["output"], result["acceptance_snapshot"]]:
                self.assertEqual(hashlib.sha256(Path(asset["path"]).read_bytes()).hexdigest(), asset["sha256"])
            self.assertEqual(result["contract"]["segments"][0]["start"], 1)
            self.assertFalse(result["uploaded"])
            with self.assertRaisesRegex(ValueError, "overwrite"):
                producer.execute(contract, output, receipt, snapshot)
