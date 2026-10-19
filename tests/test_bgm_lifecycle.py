"""Unit tests for PRD-002 / ADR-003: Apple Loops BGM engine."""
import json
import subprocess
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))

import bgm_lifecycle
from bgm_lifecycle import (
    APPLE_LOOPS_ROOT,
    CAF_INFO_UUID,
    compose,
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

    def test_scan_rejects_zero_frame_caf(self):
        pack = self.root / "Apple" / "01 Test Pack"
        pack.mkdir(parents=True)
        _make_caf(pack / "Empty Loop.caf", frames=0)
        catalog = scan_catalog(library_root=self.root)
        self.assertEqual(catalog["total_files"], 0)

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

    def test_recommends_resamplable_stereo_rates(self):
        result = recommend(self._catalog(sample_rate=48000.0), {
            "mood": ["relaxed"], "video_duration_seconds": 20,
        })
        self.assertEqual(len(result["candidates"]), 1)

    def test_recommends_rejects_invalid_sample_rate(self):
        result = recommend(self._catalog(sample_rate=0.0), {
            "mood": ["relaxed"], "video_duration_seconds": 20,
        })
        self.assertEqual(result["candidates"], [])


class BGMComposeTests(unittest.TestCase):
    def _run_compose(self, **kwargs):
        with mock.patch.object(bgm_lifecycle, "_ensure_swift_binary") as ensure_binary, \
             mock.patch.object(bgm_lifecycle.subprocess, "run") as run:
            ensure_binary.return_value = Path("/fake/swift-bgm")
            run.return_value = mock.Mock(returncode=0, stdout="{}", stderr="")
            compose(
                Path("/test/loop.caf"),
                Path("/test/video.mp4"),
                Path("/test/output.mp4"),
                **kwargs,
            )
        return run.call_args.args[0]

    def test_compose_forwards_explicit_fade_out_start(self):
        command = self._run_compose(fade_out_start=17.5)
        self.assertIn("--fade-out-start", command)
        self.assertEqual(command[command.index("--fade-out-start") + 1], "17.5")

    def test_compose_uses_duration_derived_fade_out_start_by_default(self):
        command = self._run_compose()
        self.assertNotIn("--fade-out-start", command)

    def test_compose_converts_timeout_to_runtime_error(self):
        with mock.patch.object(bgm_lifecycle, "_ensure_swift_binary"), \
             mock.patch.object(
                 bgm_lifecycle.subprocess,
                 "run",
                 side_effect=subprocess.TimeoutExpired(cmd="swift-bgm", timeout=300),
             ):
            with self.assertRaisesRegex(RuntimeError, "compose timed out after 300 seconds"):
                compose(Path("/test/loop.caf"), Path("/test/video.mp4"), Path("/test/output.mp4"))


class BGMStandaloneLifecycleTests(unittest.TestCase):
    """PRD-004: standalone compose with --managed registers lifecycle artifacts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.cfg_path = self.root / "creative.config.json"
        self.config = {"project": {"id": "demo"}, "storage": {
            "workspaceRoot": ".creative", "objectRoot": ".creative/objects",
            "releaseRoot": "creative-releases", "publicationRoot": "creative-publications"}}
        self.cfg_path.write_text(json.dumps(self.config))

    def _prepare_inputs(self):
        loop = self.root / "loop.caf"; loop.write_bytes(b"caf-loop-bytes")
        video = self.root / "preview.mp4"; video.write_bytes(b"video-bytes")
        output = self.root / ".creative" / "bgm-compose.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        return loop, video, output

    def _run_managed_compose(self, fail_registration=False):
        import app_store_creative
        loop, video, output = self._prepare_inputs()
        receipt = {"output": str(output), "final_native_lufs": -16.0,
                   "final_native_guarded_peak_dbtp": -1.2, "duration_seconds": 20.0,
                   "restored_priming_frames": 2112}
        def fake_compose(**kwargs):
            output.write_bytes(b"composed-bytes")
            return dict(receipt)
        args = app_store_creative.build_parser().parse_args([
            "bgm", "--repo", str(self.root), "compose",
            "--loop", str(loop), "--video", str(video), "--output", str(output),
            "--managed",
        ])
        import bgm_lifecycle
        from artifact_lifecycle import Lifecycle
        if fail_registration:
            original_register = Lifecycle.register
            def failing_register(self, attempt_id, source, role, **kwargs):
                if role == "preview":
                    raise RuntimeError("simulated registration failure")
                return original_register(self, attempt_id, source, role, **kwargs)
            context = mock.patch.object(Lifecycle, "register", failing_register)
            with context, mock.patch.object(bgm_lifecycle, "compose", side_effect=fake_compose):
                import importlib
                importlib.reload(app_store_creative)
                app_store_creative.run(args)
            return None, loop, video, output
        else:
            with mock.patch.object(bgm_lifecycle, "compose", side_effect=fake_compose):
                import importlib
                importlib.reload(app_store_creative)
                result = app_store_creative.run(args)
            return result, loop, video, output

    def test_managed_compose_registers_lifecycle_closure(self):
        from artifact_lifecycle import Lifecycle
        result, _, _, output = self._run_managed_compose()
        self.assertEqual(result["status"], "ok")
        artifact_ref = result["artifact"]
        self.assertIn("artifact_id", artifact_ref)
        core = Lifecycle(self.root, self.config, self.cfg_path)
        composed = core.verify_artifact(artifact_ref["artifact_id"])
        self.assertEqual(composed["role"], "preview")
        self.assertEqual(core.object_path(composed["sha256"]).read_bytes(), b"composed-bytes")
        status = core.status(artifact_ref["run_id"])
        self.assertEqual(status["attempts"][0]["outcome"]["status"], "succeeded")
        closure = core._closure([composed["id"]])
        roles = {item["role"] for item in closure.values()}
        self.assertIn("capture", roles)  # loop + video inputs registered
        self.assertIn("producer-evidence", roles)  # receipt registered

    def test_managed_compose_failure_aborts_without_partial_registration(self):
        from artifact_lifecycle import Lifecycle
        with self.assertRaisesRegex(RuntimeError, "simulated registration failure"):
            self._run_managed_compose(fail_registration=True)
        core = Lifecycle(self.root, self.config, self.cfg_path)
        outcomes = list((core.paths.workspace / "records" / "attempts").glob("*/outcome.json"))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(json.loads(outcomes[0].read_text())["status"], "failed")
        composed = self.root / ".creative" / "bgm-compose.mp4"
        self.assertFalse(composed.exists(), "workspace output must be removed on registration failure")


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
