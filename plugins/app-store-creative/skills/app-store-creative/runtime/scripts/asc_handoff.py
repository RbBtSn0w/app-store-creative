"""Prepare a local, hash-bound handoff for the official ASC agent."""
import json
from pathlib import Path
import validator


def prepare_handoff(root: Path, write: bool = False) -> dict:
    lock_file = root / ".creative/release-lock.json"
    if not lock_file.is_file():
        raise ValueError("Run verify before preparing an ASC handoff")
    lock = json.loads(lock_file.read_text())
    if lock.get("status") != "PASS":
        raise ValueError("Release validation must pass")
    cfg_path = Path(lock.get("config_path", root / "creative.config.json"))
    if validator.compute_sha256(cfg_path) != lock.get("config_hash"):
        raise ValueError("Configuration changed; run verify again")
    art = Path(lock["artifacts_dir"])
    for name, evidence in lock["assets"].items():
        path = (art / name).resolve()
        if not path.is_relative_to(art.resolve()) or validator.compute_sha256(path) != evidence["sha256"]:
            raise ValueError(f"Artifact changed or escaped output directory: {name}")
    for name, digest in lock.get("source_hashes", {}).items():
        if validator.compute_sha256(root / name) != digest:
            raise ValueError("Source recording changed; regenerate and verify")
    fresh = validator.run_validation(root, cfg_path, art, write_lockfile=False)
    if fresh["status"] != "PASS":
        raise ValueError("Current artifact validation failed")
    config = json.loads(cfg_path.read_text())
    screenshots = []
    for name in validator.declared_screenshots(config):
        locale, target, filename = name.split("/")
        screenshots.append({"locale": locale, "target": target,
                            "order": [c["id"] for c in config["cards"]].index(Path(filename).stem) + 1,
                            "path": str((art / name).resolve()), **lock["assets"][name]})
    previews = [{"path": str((art / name).resolve()),
                 "locales": validator.preview_locales(config),
                 "poster_frame_time_code": config.get("previewVideo", {}).get("posterFrameTimeCode"),
                 **evidence}
                for name, evidence in lock["assets"].items() if evidence.get("type") == "video"]
    package = {"schema_version": 1, "executor": "official-asc-plugin", "remote_write": False,
               "project": config.get("project", {}), "publishing": config.get("publishing", {}),
               "release_lock_sha256": validator.compute_sha256(lock_file),
               "design_approval_required": True, "upload_approval_required": True,
               "approvals": "pending", "screenshots": screenshots, "previews": previews,
               "required_asc_actions": ["Resolve target version and localization IDs",
                   "Confirm design and separate upload approval for these hashes",
                   "Upload through official ASC plugin", "Audit remote processing state and asset order"]}
    result = {"mode": "handoff" if write else "dry-run", "status": "awaiting_asc",
              "uploaded": False, "assets_count": len(screenshots) + len(previews), "handoff": package}
    if write:
        path = root / ".creative/asc-handoff.json"
        path.write_text(json.dumps(package, indent=2) + "\n")
        result["handoff_path"] = str(path)
    return result
