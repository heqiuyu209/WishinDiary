"""Fixed-path, aggregate-only view of an independently generated backtest."""
from datetime import date, datetime
import json
import logging
import math
import re

from app.core.config import settings
from app.ml.forecast_evaluation import MODEL_KEYS, pipeline_fingerprint

logger = logging.getLogger(__name__)
GROUP_LABELS = {
    "history": ("0–3 条", "4–7 条", "8 条以上"),
    "volatility": ("低（≤2 天）", "中（2–5 天）", "高（>5 天）"),
    "missing_bleeding": ("无缺失", "部分缺失（<50%）", "缺失 ≥50%"),
}


def _count(value) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise ValueError("Invalid aggregate sample count")
    return value


def _reject_constant(value):
    raise ValueError("Non-finite JSON value")


def _metrics(values, allowed) -> dict:
    if not isinstance(values, dict):
        raise ValueError("Invalid metrics")
    output = {}
    for key in allowed:
        value = values.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            if key != "bias_days" and value < 0:
                raise ValueError("Negative error/interval metric")
            if (key.endswith("_pct") or key.startswith("hit_rate")) and value > 100:
                raise ValueError("Invalid percentage")
            output[key] = value
    return output


def _scores(values) -> dict:
    samples = _count(values["samples"])
    models = values.get("models", {})
    result = {"samples": samples, "models": {}}
    if samples:
        result["models"] = {
            key: _metrics(models[key], ("mae", "rmse", "bias_days", "hit_rate_within_2d", "hit_rate_within_3d"))
            for key in MODEL_KEYS if key in models
        }
    return result


def read_forecast_report() -> dict:
    path = settings.model_abs_path.parent / "forecast_evaluation_report.json"
    if not path.exists():
        return {"available": False, "message": "尚未生成完整流程回测报告"}
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError("Oversized backtest report")
        report = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
        if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
            raise ValueError("Unsupported backtest schema")
        dataset = report["dataset"]
        if dataset["source"] not in {"synthetic", "authorized_csv", "authorized_database"}:
            raise ValueError("Unknown data source")
        evaluation = report["evaluation"]
        protocols = {}
        for name in ("existing_users", "unseen_users"):
            values = evaluation["protocols"][name]
            parsed = _scores(values)
            parsed["intervals"] = {}
            for method in ("rf_personalized", "basic_stats"):
                interval = values.get("intervals", {}).get(method)
                if interval is not None:
                    parsed["intervals"][method] = {
                        "samples": _count(interval["samples"]),
                        **_metrics(interval, ("coverage_pct", "mean_width_days")),
                    }
            parsed["groups"] = {}
            for axis, labels in GROUP_LABELS.items():
                buckets = values.get("groups", {}).get(axis, [])
                if not isinstance(buckets, list) or len(buckets) > len(labels):
                    raise ValueError("Invalid group summaries")
                parsed["groups"][axis] = [
                    {"label": bucket["label"], **_scores(bucket)}
                    for bucket in buckets if bucket.get("label") in labels
                ]
            for key in ("n_splits", "training_samples", "excluded_unseen_cases", "skipped_empty_folds"):
                if key in values:
                    parsed[key] = _count(values[key])
            protocols[name] = parsed
        digest = report["pipeline_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid pipeline digest")
        metadata = report.get("metadata", {})
        commit = str(metadata.get("git_commit", ""))
        generated_at = str(metadata.get("generated_at", ""))
        return {
            "available": True,
            "pipeline_matches_report": pipeline_fingerprint() == digest,
            "generated_at": datetime.fromisoformat(generated_at).isoformat() if generated_at else "",
            "git_commit": commit if re.fullmatch(r"[a-f0-9]{7,40}", commit) else "",
            "cutoff": date.fromisoformat(evaluation["cutoff"]).isoformat(),
            "dataset": {"source": dataset["source"], "total_cycles": _count(dataset["total_cycles"]),
                        "n_users": _count(dataset["n_users"])},
            "protocols": protocols,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        logger.warning("Full-pipeline backtest report could not be read")
        return {"available": False, "message": "完整流程回测报告无效，请重新生成"}
