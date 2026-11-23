"""Featuring nomination field contract and ASC JSON:API adapter."""
from datetime import datetime, timezone
import ipaddress
import json
import os
import re
import subprocess
from urllib.parse import parse_qsl, urlsplit

FLAGS = {
    "name": "name", "description": "description", "type": "type",
    "publishStartDate": "publish-start-date", "publishEndDate": "publish-end-date",
    "deviceFamilies": "device-families", "locales": "locales",
    "supportedTerritories": "supported-territories", "supplementalMaterialsUris": "supplemental-materials-uris",
    "inAppEventIds": "in-app-events", "hasInAppEvents": "has-in-app-events",
    "launchInSelectMarketsFirst": "launch-in-select-markets-first", "preOrderEnabled": "pre-order-enabled",
}
REQUIRED = ("name", "description", "type", "publishStartDate")
RELATIONS = {"relatedApps": ("appIds", "apps"), "supportedTerritories": ("supportedTerritories", "territories"),
             "inAppEvents": ("inAppEventIds", "appEvents")}
LIST_FIELDS = {"deviceFamilies", "locales", "supportedTerritories", "supplementalMaterialsUris", "inAppEventIds"}
BOOL_FIELDS = {"hasInAppEvents", "preOrderEnabled", "launchInSelectMarketsFirst"}


def date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", value):
        raise ValueError("Expected RFC3339 timestamp with timezone")
    return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def strings(values, field):
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() or "," in v or "\x00" in v for v in values):
        raise ValueError(f"Invalid list: {field}")
    return sorted(set(values))


def public_uri(value):
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("Invalid supplemental material URI")
    parts = urlsplit(value)
    host = parts.hostname or ""
    if parts.scheme != "https" or not host or "." not in host or parts.username is not None or parts.password is not None:
        raise ValueError("Expected a shareable HTTPS supplementalMaterialsUris link")
    sensitive = {"token", "key", "signature", "sig", "password", "auth", "credential", "jwt"}
    query_keys = {k.lower() for k, _ in parse_qsl(parts.query)}
    if host.endswith((".local", ".localhost", ".internal")) or any(
            any(word in key for word in sensitive) for key in query_keys):
        raise ValueError("Use a public material link without private host or query credentials")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("Private material host")


def normalize(payload):
    if not isinstance(payload, dict) or set(payload) - FLAGS.keys():
        raise ValueError("Unknown nomination payload field")
    result = {}
    for field, value in payload.items():
        if field in LIST_FIELDS:
            value = strings(value, field)
            if field == "supplementalMaterialsUris":
                for uri in value:
                    public_uri(uri)
            if field == "deviceFamilies" and set(value) - {"IPHONE", "IPAD", "MAC", "APPLE_TV", "APPLE_WATCH", "VISION"}:
                raise ValueError("Unknown deviceFamilies value")
            if field == "supportedTerritories" and any(not re.fullmatch("[A-Z]{3}", v) for v in value):
                raise ValueError("Expected ASC territory IDs")
            if field == "locales" and any(not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", v) for v in value):
                raise ValueError("Invalid locale")
        elif field in BOOL_FIELDS:
            if type(value) is not bool:
                raise ValueError(f"Expected boolean: {field}")
        elif field in ("publishStartDate", "publishEndDate"):
            value = date(value)
        elif not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError(f"Expected text: {field}")
        result[field] = value
    if "type" in result and result["type"] not in {"APP_LAUNCH", "APP_ENHANCEMENTS", "NEW_CONTENT"}:
        raise ValueError("Unknown nomination type")
    if "publishEndDate" in result and "publishStartDate" in result:
        if datetime.fromisoformat(result["publishEndDate"]) < datetime.fromisoformat(result["publishStartDate"]):
            raise ValueError("publishEndDate precedes publishStartDate")
    if result.get("inAppEventIds") and result.get("hasInAppEvents") is False:
        raise ValueError("inAppEventIds contradict hasInAppEvents")
    return result


def command(plan):
    prefix = ["asc", "--profile", plan["target"]["profileRef"], "nominations"]
    if plan["operation"] == "create_draft":
        args = ["create", "--app", ",".join(plan["target"]["appIds"])]
    else:
        args = ["update", "--id", plan["remoteId"]]
    args.append("--submitted=true" if plan["operation"] == "submit" else "--submitted=false")
    for key, value in plan["changes"].items():
        if isinstance(value, list):
            if not value:
                raise ValueError(f"unsupported_clear: {key}")
            value = ",".join(value)
        if type(value) is bool:
            args.append("--" + FLAGS[key] + "=" + str(value).lower())
        else:
            # ASC expands @file and @env values. Double a literal leading @.
            args.extend(["--" + FLAGS[key], "@" + value if value.startswith("@") else value])
    return prefix + args + ["--output", "json"]


def read_asc(target, *args):
    proc = subprocess.run(["asc", "--profile", target["profileRef"], *args, "--output", "json"],
                          capture_output=True, timeout=45, check=False, env={**os.environ, "ASC_READ_ONLY": "1"})
    if proc.returncode:
        raise ValueError(f"ASC read failed ({args[0]} {args[1]}, exit {proc.returncode})")
    return proc.stdout


def view(target, rid):
    return read_asc(target, "nominations", "view", "--id", rid, "--include", ",".join(RELATIONS),
                    "--related-apps-limit", "50", "--supported-territories-limit", "200", "--in-app-events-limit", "50")


def resource(raw):
    data = json.loads(raw).get("data")
    if (not isinstance(data, dict) or data.get("type") != "nominations"
            or not isinstance(data.get("id"), str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", data["id"])):
        raise ValueError("Missing nomination resource identity")
    return data


def snapshot(raw, target, rid):
    item = resource(raw)
    if item["id"] != rid:
        raise ValueError("Remote nomination ID mismatch")
    attrs = item.get("attributes", {})
    if not isinstance(attrs, dict):
        raise ValueError("Incomplete nomination attributes")
    payload = {key: attrs[key] for key in FLAGS if attrs.get(key) is not None}
    for field, (key, expected_type) in RELATIONS.items():
        rel = item.get("relationships", {}).get(field, {})
        rows = rel.get("data")
        if not isinstance(rows, list) or rel.get("links", {}).get("next"):
            raise ValueError(f"Incomplete relationship: {field}")
        if rel.get("meta", {}).get("paging", {}).get("total", len(rows)) != len(rows):
            raise ValueError(f"Truncated relationship: {field}")
        if any(not isinstance(r, dict) or r.get("type") != expected_type for r in rows):
            raise ValueError(f"Incorrect relationship type: {field}")
        ids = strings([r["id"] for r in rows], field)
        if key == "appIds":
            if ids != target["appIds"]:
                raise ValueError("Related apps differ from target")
        else:
            payload[key] = ids
    for field in ("publishStartDate", "publishEndDate"):
        if field in payload:
            payload[field] = date(payload[field])
    for field in LIST_FIELDS & payload.keys():
        payload[field] = strings(payload[field], field)
    if not isinstance(attrs.get("state"), str) or not all(payload.get(k) for k in REQUIRED):
        raise ValueError("Incomplete nomination attributes")
    return {"remoteId": rid, "state": attrs.get("state"), "payload": payload,
            "modifiedAt": attrs.get("lastModifiedDate"), "submittedDate": attrs.get("submittedDate")}
