"""Prospective evaluation of the exact online point/interval calculation.

Models are frozen at a common calendar cutoff. A user's personal history grows
only as earlier cycle lengths become known. Nothing is written to the database.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupKFold

from app.features.cycle_feature_engineering import (
    _is_healthy_cycle, _normalize_cycle_frame, build_prediction_feature_row, prepare_ml_history,
)
from app.ml.basic_prediction import build_basic_prediction
from app.ml.contract import FEATURE_NAMES
from app.services.cycle_prediction_service import CyclePredictionService

MODEL_KEYS = ("online_pipeline", "mean3", "median3", "ewma")
RF_PARAMETERS = {"n_estimators": 200, "random_state": 42, "max_depth": 8}
EWMA_ALPHA = 0.5


@dataclass
class ForecastCase:
    user_id: int
    anchor: pd.Timestamp
    actual_length: float
    history: pd.DataFrame
    ml_history: pd.DataFrame
    target_is_healthy: bool


def pipeline_fingerprint() -> str:
    """Identify the evaluated calculation, independently of a deployed weight file."""
    root = Path(__file__).resolve().parents[1]
    paths = ("ml/forecast_evaluation.py", "ml/basic_prediction.py", "ml/contract.py",
             "features/cycle_feature_engineering.py", "services/cycle_prediction_service.py",
             "services/prediction_service.py")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode() + b"\0" + (root / path).read_bytes() + b"\0")
    return digest.hexdigest()


def build_forecast_cases(raw_cycles: pd.DataFrame) -> list[ForecastCase]:
    required = {"user_id", "start_date", "cycle_length", "bleeding_days"}
    if not required.issubset(raw_cycles.columns):
        raise ValueError("Cycles require user_id, start_date, cycle_length and bleeding_days")
    frame = _normalize_cycle_frame(raw_cycles)
    if frame.empty or frame[["user_id", "start_date"]].isna().any().any():
        raise ValueError("Cycles require valid user IDs and start dates")
    if ((frame.user_id <= 0) | (frame.user_id % 1 != 0)).any():
        raise ValueError("User IDs must be positive integers")
    if frame.start_date.dt.tz is not None or (frame.start_date != frame.start_date.dt.normalize()).any():
        raise ValueError("Cycle anchors must be calendar dates without times or timezones")
    if frame.duplicated(["user_id", "start_date"]).any():
        raise ValueError("Duplicate cycle anchors must be resolved before evaluation")
    cases = []
    for user_id, group in frame.groupby("user_id", sort=True):
        group = group.sort_values("start_date").reset_index(drop=True)
        known_length = np.isfinite(group.cycle_length) & (group.cycle_length > 0)
        available_at = group.start_date + pd.to_timedelta(group.cycle_length.where(known_length), unit="D")
        for index, row in group.iterrows():
            if not known_length.iloc[index]:
                continue
            anchor = row.start_date
            history = group.loc[(group.start_date < anchor) & (available_at <= anchor)].copy()
            if history.empty:
                continue
            cases.append(ForecastCase(
                int(user_id), anchor, float(row.cycle_length), history,
                prepare_ml_history(history), _is_healthy_cycle(row),
            ))
    return sorted(cases, key=lambda case: (case.anchor, case.user_id))


def predict_case(case: ForecastCase, predictor: CyclePredictionService) -> dict:
    """Use the same history gate, shrinkage, rounding, clipping and CI as the API."""
    anchor = case.anchor.date()
    history = case.ml_history
    if len(history) >= 4:
        prediction = predictor.predict(
            build_prediction_feature_row(history, anchor), anchor,
            n_complete_cycles=len(history), user_mean=float(history.cycle_length.mean()),
        )
        method = "rf_personalized"
    else:
        prediction = build_basic_prediction(case.history.to_dict("records"), anchor)
        history = case.history.loc[case.history.cycle_length.between(15, 60)]
        if history.empty:
            history = case.history.tail(1)
        method = "basic_stats"
    if prediction is None:
        raise ValueError("The online pipeline could not predict an eligible case")
    lengths = history.cycle_length.to_numpy(dtype=float)
    smooth = float(lengths[0])
    for length in lengths[1:]:
        smooth = EWMA_ALPHA * float(length) + (1 - EWMA_ALPHA) * smooth
    def bounded(value):
        return max(21, min(45, int(round(float(value)))))
    return {
        "actual": case.actual_length,
        "predictions": {
            "online_pipeline": prediction["predicted_cycle_length"],
            "mean3": bounded(np.mean(lengths[-3:])),
            "median3": bounded(np.median(lengths[-3:])),
            "ewma": bounded(smooth),
        },
        "interval": prediction.get("confidence_interval"),
        "method": method,
        "history_count": len(case.ml_history),
        "history_std": float(np.std(lengths)),
        "missing_bleeding_ratio": float(history.bleeding_days.isna().mean()),
    }


def _point_scores(records: list[dict]) -> dict:
    if not records:
        return {"samples": 0, "models": {}}
    actual = np.array([record["actual"] for record in records])
    models = {}
    for name in MODEL_KEYS:
        error = np.array([record["predictions"][name] for record in records]) - actual
        models[name] = {
            "mae": round(float(np.abs(error).mean()), 4),
            "rmse": round(float(np.sqrt(np.square(error).mean())), 4),
            "bias_days": round(float(error.mean()), 4),
            "hit_rate_within_2d": round(float((np.abs(error) <= 2).mean() * 100), 2),
            "hit_rate_within_3d": round(float((np.abs(error) <= 3).mean() * 100), 2),
        }
    return {"samples": len(records), "models": models}


def summarize_forecasts(records: list[dict]) -> dict:
    summary = _point_scores(records)
    intervals = {}
    for method in ("rf_personalized", "basic_stats"):
        rows = [record for record in records if record["method"] == method and record["interval"]]
        if rows:
            intervals[method] = {
                "samples": len(rows),
                "coverage_pct": round(100 * sum(
                    row["interval"]["low"] <= row["actual"] <= row["interval"]["high"]
                    for row in rows) / len(rows), 2),
                "mean_width_days": round(float(np.mean([
                    row["interval"]["high"] - row["interval"]["low"] for row in rows])), 4),
            }
    summary["intervals"] = intervals
    buckets = {
        "history": (("0–3 条", lambda r: r["history_count"] < 4),
                    ("4–7 条", lambda r: 4 <= r["history_count"] < 8),
                    ("8 条以上", lambda r: r["history_count"] >= 8)),
        "volatility": (("低（≤2 天）", lambda r: r["history_std"] <= 2),
                       ("中（2–5 天）", lambda r: 2 < r["history_std"] <= 5),
                       ("高（>5 天）", lambda r: r["history_std"] > 5)),
        "missing_bleeding": (("无缺失", lambda r: r["missing_bleeding_ratio"] == 0),
                             ("部分缺失（<50%）", lambda r: 0 < r["missing_bleeding_ratio"] < 0.5),
                             ("缺失 ≥50%", lambda r: r["missing_bleeding_ratio"] >= 0.5)),
    }
    summary["groups"] = {
        axis: [{"label": label, **_point_scores([row for row in records if include(row)])}
               for label, include in definitions]
        for axis, definitions in buckets.items()
    }
    return summary


def run_forecast_backtest(raw_cycles: pd.DataFrame, *, test_fraction: float = 0.2,
                          n_splits: int = 5, cutoff=None, model_factory=None) -> dict:
    """Evaluate seen/unseen users with training labels available at a fixed cutoff.

    Unseen means absent from global RF training, not necessarily lacking personal
    records. Point baselines share each case and the online 21–45 day clipping.
    """
    if not 0 < test_fraction < 1 or n_splits < 2:
        raise ValueError("Invalid backtest fraction or fold count")
    cases = build_forecast_cases(raw_cycles)
    if len(cases) < 2:
        raise ValueError("Backtesting requires at least two eligible forecast cases")
    if cutoff is None:
        index = min(len(cases) - 1, max(1, int(len(cases) * (1 - test_fraction))))
        cutoff = cases[index].anchor
    cutoff = pd.Timestamp(cutoff)
    if pd.isna(cutoff):
        raise ValueError("Backtesting requires a valid calendar cutoff")
    train_cases = [case for case in cases if case.target_is_healthy and len(case.ml_history) >= 3
                   and case.anchor < cutoff
                   and case.anchor + pd.Timedelta(days=case.actual_length) <= cutoff]
    test_cases = [case for case in cases if case.anchor >= cutoff]
    if not train_cases or not test_cases:
        raise ValueError("The cutoff leaves no usable training or test cases")
    factory = model_factory or (lambda: RandomForestRegressor(**RF_PARAMETERS))

    def fit(selected):
        features = [build_prediction_feature_row(case.ml_history, case.anchor.date()) for case in selected]
        model = factory()
        model.fit(pd.DataFrame(features, columns=FEATURE_NAMES), [case.actual_length for case in selected])
        return CyclePredictionService(model=model)

    predictor = fit(train_cases)
    seen_users = {case.user_id for case in train_cases}
    existing = [predict_case(case, predictor) for case in test_cases if case.user_id in seen_users]
    existing_summary = summarize_forecasts(existing)
    existing_summary["training_samples"] = len(train_cases)
    existing_summary["excluded_unseen_cases"] = sum(case.user_id not in seen_users for case in test_cases)

    users = sorted({case.user_id for case in cases})
    unseen, folds, empty_folds = [], 0, 0
    if len(users) >= 2:
        for _, held_positions in GroupKFold(n_splits=min(n_splits, len(users))).split(
            np.zeros((len(users), 1)), groups=users,
        ):
            held_users = {users[int(index)] for index in held_positions}
            prefix = [case for case in train_cases if case.user_id not in held_users]
            targets = [case for case in test_cases if case.user_id in held_users]
            if not prefix or not targets:
                empty_folds += 1
                continue
            predictor = fit(prefix)
            unseen.extend(predict_case(case, predictor) for case in targets)
            folds += 1
    unseen_summary = summarize_forecasts(unseen)
    unseen_summary["n_splits"] = folds
    unseen_summary["skipped_empty_folds"] = empty_folds
    return {
        "available": True,
        "cutoff": cutoff.date().isoformat(),
        "candidate_samples": len(cases),
        "training_labels_available_through": max(
            case.anchor + pd.Timedelta(days=case.actual_length) for case in train_cases
        ).date().isoformat(),
        "parameters": {"rf": RF_PARAMETERS, "shrinkage_k": CyclePredictionService.SHRINKAGE_K,
                       "ewma_alpha": EWMA_ALPHA, "history_limit": 50, "ml_min_history": 4},
        "protocols": {"existing_users": existing_summary, "unseen_users": unseen_summary},
    }
