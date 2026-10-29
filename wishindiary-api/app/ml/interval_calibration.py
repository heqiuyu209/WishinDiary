"""Offline absolute-residual calibration; temporal data has no IID guarantee."""
from fractions import Fraction
import math

import numpy as np

INTERVAL_METHODS = ("rf_personalized", "basic_stats")


def fit_interval_calibrators(records: list[dict], coverage: float = 0.9) -> dict:
    """Fit each online path separately, using only completed calibration labels.

    Select the ceil((n + 1) * coverage)-th absolute residual without interpolation.
    If that order statistic is unavailable, report insufficiency rather than cap
    the rank or emit a misleading finite interval. No residuals are persisted.
    """
    if isinstance(coverage, bool) or not math.isfinite(coverage) or not 0 < coverage < 1:
        raise ValueError("Target interval coverage must be between zero and one")
    probability = Fraction(str(coverage))
    fits = {}
    for method in INTERVAL_METHODS:
        errors = sorted(abs(float(row["actual"]) - float(row["predictions"]["online_pipeline"]))
                        for row in records if row["method"] == method)
        if any(not math.isfinite(value) for value in errors):
            raise ValueError("Calibration errors must be finite")
        count = len(errors)
        numerator = (count + 1) * probability.numerator
        rank = (numerator + probability.denominator - 1) // probability.denominator
        fits[method] = {"samples": count, "rank": rank, "available": rank <= count}
        if rank <= count:
            fits[method]["radius_days"] = errors[rank - 1]
    return fits


def apply_interval_calibration(records: list[dict], fits: dict) -> list[dict]:
    """Apply frozen radii to point predictions without reading test outcomes."""
    results = []
    for row in records:
        fit = fits[row["method"]]
        interval = None
        if fit["available"]:
            point = row["predictions"]["online_pipeline"]
            radius = fit["radius_days"]
            # Do not clip interval endpoints to the point estimator's 21–45 gate.
            interval = {"low": point - radius, "high": point + radius}
        results.append({**row, "calibrated_interval": interval})
    return results


def interval_scores(records: list[dict], key: str) -> dict:
    rows = [row for row in records if row.get(key) is not None]
    if not rows:
        return {"samples": 0}
    return {
        "samples": len(rows),
        "coverage_pct": round(100 * sum(row[key]["low"] <= row["actual"] <= row[key]["high"]
                                         for row in rows) / len(rows), 2),
        "mean_width_days": round(float(np.mean([row[key]["high"] - row[key]["low"]
                                                 for row in rows])), 4),
    }


def summarize_interval_calibration(records: list[dict], fits: list[dict], coverage: float) -> dict:
    """Compare original and calibrated intervals on exactly the same test cases."""
    methods = {}
    for method in INTERVAL_METHODS:
        rows = [row for row in records if row["method"] == method]
        paired = [row for row in rows if row.get("interval") is not None
                  and row.get("calibrated_interval") is not None]
        methods[method] = {
            "fits": [fold[method] for fold in fits],
            "test_samples": len(rows),
            "unavailable_samples": sum(row.get("calibrated_interval") is None for row in rows),
            "calibrated": interval_scores(rows, "calibrated_interval"),
            "comparison": {"samples": len(paired),
                           "original": interval_scores(paired, "interval"),
                           "calibrated": interval_scores(paired, "calibrated_interval")},
        }
    return {"target_coverage_pct": coverage * 100, "methods": methods}
