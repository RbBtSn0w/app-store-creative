"""Local In-App Event brief, evidence, media and calendar checks."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import urlsplit

from record_primitives import digest, safe_id
from project_identity import require_project_identity


def require(condition, message):
    if not condition:
        raise ValueError(message)


def string(value):
    return isinstance(value, str) and bool(value.strip())


def strings(values):
    return (
        isinstance(values, list)
        and bool(values)
        and all(map(string, values))
        and len(set(values)) == len(values)
    )


def timestamp(value):
    require(
        string(value) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", value),
        f"Expected RFC3339 timestamp with offset: {value}",
    )
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def local(root, value):
    require(isinstance(value, (str, Path)) and bool(str(value)), "Expected project path")
    path = (root / value).resolve()
    require(path.is_relative_to(root), f"Path outside project: {value}")
    return path


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    data = json.loads(path.read_text(), object_pairs_hook=unique)
    require(isinstance(data, dict), f"Expected JSON object: {path.name}")
    return data


def version(data):
    require(
        type(data.get("schemaVersion")) is int and data["schemaVersion"] == 1, "Unsupported schemaVersion"
    )


def evidence(root, ref):
    path = local(root, ref["path"])
    require(digest(path) == ref["sha256"], f"Evidence digest mismatch: {ref['path']}")


def issue(code, field, actual, expected, remedy):
    return dict(code=code, field=field, actual=actual, expected=expected, remedy=remedy)


def plan(root, brief):
    version(brief)
    safe_id(brief["eventKey"])
    require(string(brief["projectId"]) and string(brief["appId"]), "Missing projectId or appId")
    config = local(root, "creative.config.json")
    if config.exists():
        cfg = load(config)
        require(require_project_identity(cfg) == brief["projectId"], "Project identity mismatch")
        if brief.get("bundleId") and cfg["project"].get("bundleId"):
            require(brief["bundleId"] == cfg["project"]["bundleId"], "Bundle identity mismatch")
    for field in ("platform", "badge", "purpose", "priority", "purchaseRequirement"):
        if field in brief:
            require(string(brief[field]), f"Expected text for {field}")
            brief[field] = brief[field].upper()
    require(brief["platform"] == "IOS", "Only IOS is supported")
    require(type(brief["timelyExperience"]) is bool, "timelyExperience must be boolean")
    if not brief["timelyExperience"]:
        require(string(brief.get("reason")), "A skipped release needs a reason")
        return "skip", []
    missing = [
        name
        for name in ("audience", "experience", "action", "buildRef", "bundleId")
        if not string(brief.get(name))
    ]
    require(isinstance(brief.get("claims", []), list), "Expected a list of claims")
    if not brief.get("claims"):
        missing.append("claims")
    for claim in brief.get("claims", []):
        require(string(claim["text"]), "Empty product claim")
        evidence(root, claim)
    if not brief.get("measurement", {}).get("decision"):
        missing.append("measurement.decision")
    return (
        "defer" if missing else "propose",
        [issue("missing-fact", name, None, "verified input", "Supply product evidence") for name in missing],
    )


def windows(schedule, territories):
    overrides = schedule.get("overrides", {})
    require(
        isinstance(overrides, dict) and set(overrides) <= set(territories),
        "Unknown schedule override territory",
    )
    result = {}
    for territory in territories:
        row = overrides.get(territory, schedule)
        publish, start, end = (timestamp(row[k]) for k in ("publishAt", "startAt", "endAt"))
        require(timedelta(0) <= start - publish <= timedelta(days=14), "Invalid preheat window")
        require(timedelta(minutes=15) <= end - start <= timedelta(days=31), "Invalid event duration")
        result[territory] = (publish, start, end)
    starts = [w[1] for w in result.values()]
    require(max(starts) - min(starts) <= timedelta(hours=48), "Regional starts exceed 48 hours")
    return result


APPROVED = {"SET_TO_PUBLISH", "PUBLISHED", "APPROVED"}
ACTIVE = APPROVED | {"DRAFT", "WAITING_FOR_REVIEW", "IN_REVIEW", "READY_FOR_REVIEW"}


def calendar(brief, snapshot, now, bound_id):
    version(snapshot)
    require(snapshot["appId"] == brief["appId"], "Inventory appId mismatch")
    require(snapshot["complete"] is True, "Inventory pagination incomplete")
    require(
        timedelta(0) <= now - timestamp(snapshot["observedAt"]) <= timedelta(hours=24),
        "Refresh inventory (maximum snapshot age 24 hours)",
    )
    require(type(snapshot["hasApprovedVersion"]) is bool, "Unknown first-version status")
    require(
        strings(snapshot["territories"]) and set(brief["territories"]) <= set(snapshot["territories"]),
        "App unavailable in requested territories",
    )
    candidate = windows(brief["schedule"], brief["territories"])
    if not bound_id:
        require(all(w[0] >= now for w in candidate.values()), "New event publish time is in the past")
    require(all(w[1] > now for w in candidate.values()), "Start must be in the future")
    seen = {}
    for row in snapshot["events"]:
        event_id = safe_id(row["eventId"])
        require(seen.get(event_id, row) == row, "Conflicting duplicate inventory row")
        seen[event_id] = row
    if bound_id:
        require(bound_id in seen, "Bound event missing from inventory")
        require(
            seen.pop(bound_id)["state"] in {"DRAFT", "REJECTED"}, "Bound event requires state-specific review"
        )
    require(
        all(row["referenceName"] != brief["referenceName"] for row in seen.values()),
        "Reference name already in use",
    )
    require(sum(row["state"] == "DRAFT" for row in seen.values()) < 50, "Draft capacity exhausted")
    approval_available = sum(row["state"] in APPROVED for row in seen.values()) < 15
    schedules = [("candidate", candidate, True)]
    for event_id, row in seen.items():
        state = row["state"]
        require(state in ACTIVE | {"PAST", "ARCHIVED", "REJECTED"}, f"Unknown inventory state {state}")
        if state in ACTIVE:
            require(strings(row["territories"]), "Missing inventory territories")
            schedules.append((event_id, windows(row["schedule"], row["territories"]), state in APPROVED))
    for index, label in ((0, "display"), (1, "activity")):
        intervals = [
            (event_id, region, times[index], times[2])
            for event_id, regions, approved in schedules
            if index or approved
            for region, times in regions.items()
        ]
        for instant in sorted({start for _, _, start, _ in intervals}):
            active = [
                (event_id, region) for event_id, region, start, end in intervals if start <= instant < end
            ]
            ids = sorted({event_id for event_id, _ in active})
            if "candidate" in ids and len(ids) > 10:
                raise ValueError(
                    f"{label} conflict at {instant.isoformat()}: {ids}, regions {sorted(set(r for _, r in active))}"
                )

    return approval_available


def media(root, value, slot):
    path = local(root, value)
    codecs = {".jpg": "mjpeg", ".jpeg": "mjpeg", ".png": "png"}
    codec = codecs.get(path.suffix.lower())
    require(codec, "Static PNG or JPEG required")
    require(0 < path.stat().st_size <= 500_000_000, "Image exceeds size limit or is empty")
    # Pin the image demuxer and decoder. A renamed video or playlist cannot be used as an image.
    demuxer = "png_pipe" if codec == "png" else "jpeg_pipe"
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-f",
            demuxer,
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    (stream,) = json.loads(probe.stdout)["streams"]
    w, h = stream["width"], stream["height"]
    x, y = (1920, 1080) if slot == "card" else (1080, 1920)
    require(
        stream["codec_name"] == codec and w * y == h * x and x <= w <= 2 * x,
        f"Wrong format or dimensions {w}x{h} for {slot}",
    )
    with path.open("rb") as source:
        if codec == "png":
            source.seek(-12, 2)
            require(source.read() == bytes.fromhex("0000000049454e44ae426082"), "Incomplete PNG")
        else:
            source.seek(-2, 2)
            require(source.read() == b"\xff\xd9", "Incomplete JPEG")
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-f",
            demuxer,
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return {"path": str(path.relative_to(root)), "sha256": digest(path), "width": w, "height": h}


def fields(brief):
    require(re.fullmatch(r"[0-9]+", brief["appId"]), "Expected numeric ASC appId")
    require(type(brief.get("requiresNewVersion", False)) is bool, "Invalid requiresNewVersion")
    if "additionalRouteScenarios" in brief:
        require(strings(brief["additionalRouteScenarios"]), "Invalid additionalRouteScenarios")
    for key, options in {
        "badge": "LIVE_EVENT PREMIERE CHALLENGE COMPETITION NEW_SEASON MAJOR_UPDATE SPECIAL_EVENT",
        "priority": "NORMAL HIGH",
        "purpose": "APPROPRIATE_FOR_ALL_USERS ATTRACT_NEW_USERS KEEP_ACTIVE_USERS_INFORMED BRING_BACK_LAPSED_USERS",
        "purchaseRequirement": "NO_COST_ASSOCIATED IN_APP_PURCHASE",
    }.items():
        require(brief[key] in options.split(), f"Invalid {key}")
    require(
        strings(brief["territories"]) and all(re.fullmatch("[A-Z]{3}", t) for t in brief["territories"]),
        "Expected distinct three-letter ASC territories",
    )
    url = urlsplit(brief["deepLink"])
    require(
        url.scheme not in ("", "file", "data", "javascript", "http")
        and (url.netloc or url.path)
        and (url.scheme != "https" or url.hostname)
        and not any(c.isspace() for c in brief["deepLink"]),
        "Provide a universal link or registered app URL",
    )
    require(
        string(brief["referenceName"]) and len(unicodedata.normalize("NFC", brief["referenceName"])) <= 64,
        "Invalid referenceName",
    )
    windows(brief["schedule"], brief["territories"])
    locales = brief["localizations"]
    require(isinstance(locales, dict) and brief["primaryLocale"] in locales, "Missing primary locale")
    for locale, row in locales.items():
        require(string(locale), "Empty locale")
        for key, limit in [("name", 30), ("shortDescription", 50), ("longDescription", 120)]:
            require(
                string(row[key]) and len(unicodedata.normalize("NFC", row[key])) <= limit,
                f"Invalid {locale}.{key} (limit {limit})",
            )


def routes(root, brief, report):
    version(report)
    for name in ("bundleId", "buildRef", "eventKey", "deepLink"):
        require(report[name] == brief[name], f"Route {name} mismatch")
    required = {"cold", "warm", "onboarding", "expired"}
    required.update(brief.get("additionalRouteScenarios", []))
    pairs = {(region, phase) for region in brief["territories"] for phase in required}
    for region, times in windows(brief["schedule"], brief["territories"]).items():
        if times[0] < times[1]:
            pairs.add((region, "preheat"))
    covered = set()
    for row in report["checks"]:
        phase = row["scenario"]
        expected = brief["destinations"].get(phase, brief["destinations"]["active"])
        require(
            string(expected)
            and row["actualDestination"] == expected
            and row["eventKey"] == brief["eventKey"],
            f"Wrong {phase} destination",
        )
        require(
            row["passed"] is True and (phase in {"preheat", "expired"} or row["actionAvailable"] is True),
            f"Route action unavailable: {phase}",
        )
        timestamp(row["observedAt"])
        evidence(root, row["evidence"])
        covered.add((row["territory"], phase))
    for phase in ("expired", "preheat"):
        if any(scenario == phase for _, scenario in pairs):
            require(string(brief["destinations"].get(phase)), f"Missing {phase} destination")
    missing = pairs - covered
    require(not missing, f"Missing route checks: {sorted(missing)}")
