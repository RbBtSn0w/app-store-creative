"""Build bounded Publisher instructions and reconcile observed ASC resources."""

from event_plan import require, safe_id, string, timestamp, version


def handoff(brief, assets, inventory, bound):
    manual = bool(brief["schedule"].get("overrides")) or brief["purchaseRequirement"] != "NO_COST_ASSOCIATED"
    mode = (
        "with-version"
        if not inventory["hasApprovedVersion"] or brief.get("requiresNewVersion")
        else "standalone"
    )
    base = ["asc", "app-events"]
    if bound:
        command = base + ["update", "--event-id", bound]
    else:
        command = base + ["create", "--app", brief["appId"]]
    for name, field in [
        ("name", "referenceName"),
        ("primary-locale", "primaryLocale"),
        ("priority", "priority"),
        ("purpose", "purpose"),
        ("event-type", "badge"),
        ("deep-link", "deepLink"),
    ]:
        command.extend(["--" + name, brief[field]])
    command += [
        "--territories",
        ",".join(brief["territories"]),
        "--purchase-requirement",
        brief["purchaseRequirement"],
    ]
    for flag, key in [("publish-start", "publishAt"), ("start", "startAt"), ("end", "endAt")]:
        command.extend(["--" + flag, brief["schedule"][key]])
    command += ["--output", "json"]
    return {
        "brief": brief,
        "assets": assets,
        "submissionMode": mode,
        "configuration": "manual-required" if manual else "cli",
        "configureArgv": None if manual else command,
        "manualFields": {"purchaseRequirement": brief["purchaseRequirement"], "schedule": brief["schedule"]}
        if manual
        else {},
        "boundEventId": bound,
        "beforeWrite": ["refresh-inventory", "reconcile-remote", "verify-operation-authorization"],
        "slots": {"card": "EVENT_CARD", "details": "EVENT_DETAILS_PAGE"},
    }


def normalized_schedule(schedule):
    def normalize_window(window):
        return {**window, **{key: timestamp(window[key]) for key in ("publishAt", "startAt", "endAt")}}

    result = normalize_window(schedule)
    result["overrides"] = {region: normalize_window(window)
                           for region, window in schedule.get("overrides", {}).items()}
    return result


def reconcile(package, snapshot, binding):
    """Accept a normalized Publisher readback; never issue a remote mutation."""
    version(snapshot)
    brief = package["brief"]
    require(
        snapshot["appId"] == brief["appId"] and snapshot["eventKey"] == brief["eventKey"],
        "Observation scope mismatch",
    )
    timestamp(snapshot["observedAt"])
    status = snapshot.get("readStatus", "ok")
    diagnostics = {
        "forbidden": "check-access",
        "rate-limited": "retry-read",
        "unavailable": "retry-read",
        "write-unknown": "reconcile-before-write",
    }
    if status in diagnostics:
        return {"status": diagnostics[status], "actions": []}
    require(status == "ok", "Unknown read status")
    rows = snapshot["matches"]
    require(isinstance(rows, list), "Expected matches array")
    if len(rows) != 1 or snapshot.get("complete") is not True:
        return {"status": "pending-reconciliation", "actions": []}
    row = rows[0]
    event_id = safe_id(row["eventId"])
    require(not binding or binding["eventId"] == event_id, "Bound event identity changed")
    require(row["referenceName"] == brief["referenceName"], "Reference name mismatch")
    for key in (
        "schedule",
        "territories",
        "deepLink",
        "badge",
        "purpose",
        "priority",
        "purchaseRequirement",
        "primaryLocale",
    ):
        expected = brief[key]
        actual = row.get(key)
        if key == "territories" and isinstance(actual, list):
            actual, expected = sorted(actual), sorted(expected)
        if key == "schedule":
            try:
                actual, expected = normalized_schedule(actual), normalized_schedule(expected)
            except (KeyError, ValueError, TypeError, AttributeError):
                return {"status": "remote-conflict", "field": key, "actions": []}
        if actual != expected:
            return {"status": "remote-conflict", "field": key, "actions": []}
    state = row["state"]
    result = {"status": "needs-review", "eventId": event_id, "remoteState": state, "actions": []}
    if state in {
        "WAITING_FOR_REVIEW",
        "IN_REVIEW",
        "SET_TO_PUBLISH",
        "PUBLISHED",
        "PAST",
        "ARCHIVED",
        "APPROVED",
    }:
        result["status"] = state.lower().replace("_", "-")
        return result
    if state == "REJECTED":
        return dict(result, status="revise", reason=row.get("reason"))
    if state not in {"DRAFT", "READY_FOR_REVIEW"}:
        return result
    remote = row["localizations"]
    require(isinstance(remote, dict), "Missing locale readback")
    extra = set(remote) - set(brief["localizations"])
    if extra:
        return dict(result, status="remote-conflict", unexpectedLocales=sorted(extra))
    for locale, desired in brief["localizations"].items():
        record = remote.get(locale)
        text = {k: desired[k] for k in ("name", "shortDescription", "longDescription")}
        if record is None:
            result["actions"].append({"action": "create-localization", "locale": locale, "text": text})
            continue
        loc_id = safe_id(record["localizationId"])
        if record.get("text") != text:
            return dict(result, status="remote-conflict", field=locale, actions=[])
        for slot in ("card", "details"):
            asset = record["assets"].get(slot)
            desired_asset = package["assets"][locale][slot]
            if asset is None:
                result["actions"].append(
                    {
                        "action": "upload",
                        "localizationId": loc_id,
                        "assetType": package["slots"][slot],
                        **desired_asset,
                    }
                )
            elif asset["state"] == "PROCESSING":
                return dict(result, status="await-delivery", actions=[])
            elif asset["state"] != "COMPLETE" or asset.get("sha256") != desired_asset["sha256"]:
                return dict(result, status="verify-asset", assetId=asset.get("assetId"), actions=[])
    if result["actions"]:
        return dict(result, status="prepare-draft")
    if not package["approvalAvailable"]:
        return dict(result, status="refresh-approval-capacity")
    submission = row.get("submission")
    permitted = {("appEvents", event_id)}
    if package["submissionMode"] == "with-version":
        version_id = brief.get("versionId")
        if not string(version_id):
            return dict(result, status="identify-version-submission")
        permitted.add(("appStoreVersions", version_id))
    if submission is None:
        return dict(result, status="locate-version-draft" if len(permitted) > 1 else "ready-for-submission")
    items = {(i["type"], i["id"]) for i in submission["items"]}
    if (
        submission["appId"] != brief["appId"]
        or submission["platform"] != "IOS"
        or not items <= permitted
        or (len(permitted) > 1 and ("appStoreVersions", version_id) not in items)
    ):
        return dict(result, status="review-submission-scope")
    if submission["state"] != "READY_FOR_REVIEW":
        return dict(result, status="observe-submission")
    return dict(
        result,
        status="resume-draft",
        submissionId=safe_id(submission["submissionId"]),
        actions=[
            {"action": "submit-existing" if ("appEvents", event_id) in items else "add-event-to-existing"}
        ],
    )
