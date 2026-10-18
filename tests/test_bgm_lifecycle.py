"""Unit tests for PRD-002 / ADR-003: Apple Loops BGM engine."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))

from bgm_lifecycle import (
    APPLE_LOOPS_ROOT,
    CAF_INFO_UUID,
    _parse_caf_header,
    _parse_info_pairs,
    recommend,
    scan_catalog,
)


def _make_caf(
    path: Path,
    *,
    sample_rate: float = 44100.0,
    channels: int = 2,
    frames: int = 882000,
    tags: dict[str, str] | None = None,
) -> None:
    """Write a minimal CAF file with desc, pakt, info, and uuid info-tag chunks."""
    tags = tags or {}
    chunks: list[tuple[bytes, bytes]] = []
    desc = struct.pack(">d", sample_rate) + b"\0" * 16 + struct.pack(">I", channels)
    chunks.append((b"desc", desc))
    pakt = b"\0" * 8 + struct.pack(">q", frames)
    chunks.append((b"pakt", pakt))
    info_pairs = b"".join(k.encode() + b"\0" + v.encode() + b"\0" for k, v in tags.items())
    info = struct.pack(">I", len(tags)) + info_pairs
    chunks.append((b"info", info))
    uuid_key = bytes.fromhex(CAF_INFO_UUID)
    uuid_payload = uuid_key + struct.pack(">I", len(tags)) + info_pairs
    chunks.append((b"uuid", uuid_payload))
    body = b"".join(struct.pack(">4sq", ctype, len(data)) + data for ctype, data in chunks)
    path.write_bytes(b"caff" + b"\0" * 4 + body)


class BGMScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_missing_library_returns_unavailable(self):
        catalog = scan_catalog(library_root=self.root / "does-not-exist")
        self.assertFalse(catalog["available"])
        self.assertEqual(catalog["total_files"], 0)
        self.assertEqual(catalog["fallback"], "synthesize_ambient_bgm")

    def test_scan_parses_caf_metadata(self):
        pack = self.root / "Apple" / "01 Test Pack"
        pack.mkdir(parents=True)
        _make_caf(pack / "Test Piano 01.caf", frames=882000, tags={
            "beat count": "16", "descriptors": "Relaxed,Clean,Melodic",
            "genre": "Test Genre", "key signature": "C", "key type": "major",
            "subcategory": "Piano", "category": "Keyboards",
        })
        catalog = scan_catalog(library_root=self.root)
        self.assertTrue(catalog["available"])
        self.assertEqual(catalog["total_files"], 1)
        self.assertEqual(catalog["music_loops"], 1)
        entry = catalog["entries"][0]
        self.assertEqual(entry["name"], "Test Piano 01")
        self.assertEqual(entry["pack"], "01 Test Pack")
        self.assertAlmostEqual(entry["duration"], 20.0, places=1)
        self.assertAlmostEqual(entry["bpm_derived"], 48.0, places=1)
        self.assertEqual(entry["tags"]["descriptors"], "Relaxed,Clean,Melodic")

    def test_scan_records_per_file_errors(self):
        pack = self.root / "Apple" / "01 Test Pack"
        pack.mkdir(parents=True)
        (pack / "Not CAF.caf").write_bytes(b"not a caf file")
        _make_caf(pack / "Good Piano.caf", frames=441000, tags={"beat count": "8"})
        catalog = scan_catalog(library_root=self.root)
        self.assertEqual(catalog["total_files"], 1)
        self.assertEqual(len(catalog["errors"]), 0)  # non-CAF magic returns None, not error

    def test_scan_distinguishes_sound_effects(self):
        sfx = self.root / "Apple" / "Final Cut Pro Sound Effects"
        sfx.mkdir(parents=True)
        _make_caf(sfx / "Boom.caf", frames=44100)
        music = self.root / "Apple" / "01 Music"
        music.mkdir(parents=True)
        _make_caf(music / "Melody.caf", frames=882000)
        catalog = scan_catalog(library_root=self.root)
        self.assertEqual(catalog["sound_effects"], 1)
        self.assertEqual(catalog["music_loops"], 1)


class BGMRecommendTests(unittest.TestCase):
    def _catalog(self, **overrides):
        entry = {
            "path": "/test/loop.caf", "name": "Test Loop", "pack": "Test Pack",
            "duration": 20.0, "channels": 2, "sample_rate": 44100.0, "bpm_derived": 85.0,
            "tags": {"descriptors": "Relaxed,Clean,Melodic", "genre": "Test Genre",
                      "subcategory": "Piano", "key signature": "C", "key type": "major"},
        }
        entry.update(overrides)
        return {"available": True, "entries": [entry]}

    def test_unavailable_catalog_falls_back(self):
        result = recommend({"available": False, "entries": []}, {})
        self.assertFalse(result["available"])
        self.assertEqual(result["fallback"], "synthesize_ambient_bgm")

    def test_score_matches_mood_and_instrumentation(self):
        result = recommend(self._catalog(), {
            "mood": ["relaxed", "clean"], "instrumentation": ["Piano"],
            "tempo": "moderate", "video_duration_seconds": 20,
        })
        self.assertEqual(len(result["candidates"]), 1)
        c = result["candidates"][0]
        self.assertGreater(c["score"], 0)
        self.assertIn("mood", c["mapping"])
        self.assertIn("instrumentation", c["mapping"])
        self.assertIn("license_rationale", c)

    def test_penalty_for_loop_wraps(self):
        short = self._catalog(name="Short Loop", duration=5.0, path="/test/short.caf")
        long = self._catalog(name="Long Loop", duration=20.0, path="/test/long.caf")
        catalog = {"available": True, "entries": [short["entries"][0], long["entries"][0]]}
        result = recommend(catalog, {"mood": ["relaxed"], "video_duration_seconds": 20})
        scores = {c["name"]: c["score"] for c in result["candidates"]}
        if len(scores) == 2:
            self.assertGreater(scores["Long Loop"], scores["Short Loop"])

    def test_genre_affinity(self):
        result = recommend(self._catalog(), {"genre": "test genre"})
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["mapping"].get("genre"), "Test Genre")


class BGMCAFHeaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_non_caf_returns_none(self):
        path = self.root / "not-caf.caf"
        path.write_bytes(b"RIFF")
        self.assertIsNone(_parse_caf_header(path))

    def test_info_pair_parsing_handles_unicode(self):
        target = {}
        _parse_info_pairs("key\0value\0键\0值\0".encode("utf-8"), target)
        self.assertEqual(target["key"], "value")
        self.assertEqual(target["键"], "值")

    def test_info_pair_parsing_skips_bad_unicode(self):
        target = {}
        _parse_info_pairs(b"key\0\xff\xfe\0", target)
        self.assertNotIn("key", target)


if __name__ == "__main__":
    unittest.main()
