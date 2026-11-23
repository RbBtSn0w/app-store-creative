"""Evaluate the predeclared product measure against scoped aggregate reports."""

from decimal import Decimal
import math

from event_plan import require, string, timestamp, version, windows


def policy(data):
    for field in ("goal", "decision", "primaryMetric", "numerator", "denominator", "window", "cohort"):
        require(string(data[field]), f"Missing measurement.{field}")
    require(data["window"] == "event_start_to_end", "Unsupported measurement window")
    require(data["numerator"] != data["denominator"], "Numerator and denominator must differ")
    require(type(data["minDenominator"]) is int and data["minDenominator"] > 0, "Invalid minimum sample")
    threshold = data["threshold"]
    require(
        type(threshold) in (int, float) and math.isfinite(threshold) and 0 <= threshold <= 1,
        "Invalid measurement threshold",
    )


def assess(brief, binding, store, product):
    measure = brief["measurement"]
    policy(measure)
    schedules = windows(brief["schedule"], brief["territories"])
    for source, report in [("store", store), ("product", product)]:
        if report is None:
            continue
        version(report)
        require(
            report["source"] == source
            and report["appId"] == brief["appId"]
            and report["eventKey"] == brief["eventKey"]
            and report["eventId"] == binding["eventId"],
            f"{source} identity mismatch",
        )
        require(
            report["window"] == measure["window"]
            and sorted(report["territories"]) == sorted(brief["territories"]),
            f"{source} window or territory mismatch",
        )
        require(
            timestamp(report["from"]) == min(w[1] for w in schedules.values())
            and timestamp(report["to"]) == max(w[2] for w in schedules.values()),
            f"{source} timestamps differ from the declared event window",
        )
        require(
            report["availability"] in {"available", "delayed", "suppressed", "not-collected"},
            f"Unknown {source} availability",
        )
        metrics = report["metrics"]
        require(
            isinstance(metrics, dict) and all(type(v) is int and v >= 0 for v in metrics.values()),
            f"Invalid {source} counts",
        )
        require(report["availability"] == "available" or not metrics, f"{source} unavailable with values")
    result = {
        "status": "insufficient-data",
        "measure": measure,
        "store": store,
        "product": product,
        "ratio": None,
        "scope": measure["cohort"],
    }
    if product is None or product["availability"] != "available":
        return result
    require(product["cohort"] == measure["cohort"], "Product cohort mismatch")
    counts = product["metrics"]
    n, d = counts.get(measure["numerator"]), counts.get(measure["denominator"])
    if n is None or d is None:
        return result
    require(n <= d, "Numerator exceeds denominator")
    if d:
        result["ratio"] = n / d
    if d >= measure["minDenominator"]:
        passed = Decimal(n) >= Decimal(str(measure["threshold"])) * d
        result["status"] = "threshold-met" if passed else "below-threshold"
    return result
