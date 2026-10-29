from datetime import date, timedelta

import pandas as pd
import pytest

from app.features.cycle_feature_engineering import build_prediction_feature_row
from app.ml.forecast_evaluation import (
    MODEL_KEYS, build_forecast_cases, pipeline_fingerprint, predict_case, run_forecast_backtest,
    summarize_forecasts,
)
from app.services.cycle_prediction_service import CyclePredictionService


def _cycles(n_users=3, lengths=(26, 28, 27, 29, 30, 26, 28, 29)):
    records = []
    for user_id in range(1, n_users + 1):
        anchor = date(2024, 1, 1)
        for index, length in enumerate(lengths):
            records.append({"user_id": user_id, "start_date": anchor,
                            "cycle_length": length, "bleeding_days": 5 if index % 2 else None})
            anchor += timedelta(days=length)
    return pd.DataFrame(records)


class ConstantModel:
    def __init__(self, value=60):
        self.value = value
        self.fitted = None

    def fit(self, X, y):
        self.fitted = (X.copy(), list(y))
        return self

    def predict(self, X):
        return [self.value] * len(X)


def test_backtest_calls_the_same_online_shrinkage_and_clipping():
    case = next(case for case in build_forecast_cases(_cycles()) if len(case.ml_history) == 4)
    predictor = CyclePredictionService(model=ConstantModel())
    direct = predictor.predict(build_prediction_feature_row(case.ml_history, case.anchor.date()),
                               case.anchor.date(), n_complete_cycles=4,
                               user_mean=float(case.ml_history.cycle_length.mean()))
    backtest = predict_case(case, predictor)
    assert backtest["predictions"]["online_pipeline"] == direct["predicted_cycle_length"] == 44
    assert backtest["interval"] == direct["confidence_interval"]
    assert backtest["method"] == "rf_personalized"


def test_cold_start_uses_personal_statistics_not_the_global_model():
    case = build_forecast_cases(_cycles())[0]
    out = predict_case(case, CyclePredictionService(model=ConstantModel(60)))
    assert out["method"] == "basic_stats"
    assert out["predictions"] == dict.fromkeys(MODEL_KEYS, 26)
    assert out["interval"]["low"] == out["interval"]["high"] == 26


def test_future_labels_and_bleeding_do_not_enter_current_features():
    frame = _cycles(n_users=1)
    target_anchor = frame.start_date.iloc[4]
    original = next(case for case in build_forecast_cases(frame) if case.anchor.date() == target_anchor)
    frame.loc[4:, "cycle_length"] = 44
    frame.loc[4:, "bleeding_days"] = 14
    changed = next(case for case in build_forecast_cases(frame) if case.anchor.date() == target_anchor)
    assert build_prediction_feature_row(original.ml_history, target_anchor) == build_prediction_feature_row(changed.ml_history, target_anchor)
    model = CyclePredictionService(model=ConstantModel())
    assert predict_case(original, model)["predictions"] == predict_case(changed, model)["predictions"]


def test_overlapping_cycle_label_is_unknown_until_that_cycle_finishes():
    frame = _cycles(n_users=1)
    frame.loc[1, "cycle_length"] = 300
    target = next(case for case in build_forecast_cases(frame) if case.anchor.date() == frame.start_date.iloc[4])
    assert 300 not in target.history.cycle_length.tolist()


def test_model_training_is_frozen_before_cutoff_and_user_folds_are_disjoint():
    frame = _cycles()
    # Unique per-user bleeding windows identify which users were in each fit.
    frame["bleeding_days"] = frame.user_id
    models = []
    def factory():
        model = ConstantModel(30)
        models.append(model)
        return model
    result = run_forecast_backtest(frame, cutoff="2024-05-01", n_splits=3, model_factory=factory)
    assert len(models) == 4  # common prefix plus one model per held-out user
    assert result["training_labels_available_through"] <= result["cutoff"]
    assert set(models[0].fitted[0].lag_1_bleeding) == {1, 2, 3}
    assert all(len(set(model.fitted[0].lag_1_bleeding)) == 2 for model in models[1:])
    for protocol in result["protocols"].values():
        assert protocol["samples"] == 9
        assert set(protocol["models"]) == set(MODEL_KEYS)
        for buckets in protocol["groups"].values():
            assert sum(bucket["samples"] for bucket in buckets) == protocol["samples"]


def test_unfinished_training_target_does_not_enter_any_fold():
    frame = _cycles()
    # This target starts before cutoff but finishes afterward; do not fit its label.
    frame.loc[frame.start_date == date(2024, 4, 20), "cycle_length"] = 44
    models = []
    def factory():
        model = ConstantModel(30)
        models.append(model)
        return model
    run_forecast_backtest(frame, cutoff="2024-05-01", model_factory=factory)
    assert all(44 not in model.fitted[1] for model in models)


def test_insufficient_or_ambiguous_data_fails_explicitly():
    with pytest.raises(ValueError, match="Duplicate"):
        build_forecast_cases(pd.concat([_cycles(), _cycles().iloc[:1]]))
    with pytest.raises(ValueError, match="cutoff"):
        run_forecast_backtest(_cycles(), cutoff="2024-01-01")
    with pytest.raises(ValueError, match="Invalid"):
        run_forecast_backtest(_cycles(), test_fraction=0)
    with pytest.raises(ValueError, match="at least two"):
        run_forecast_backtest(_cycles(n_users=1, lengths=(28,)))
    assert len(pipeline_fingerprint()) == 64


def test_interval_coverage_uses_actual_values_and_separates_basic_estimator():
    def record(actual, method, low, high):
        return {"actual": actual, "predictions": dict.fromkeys(MODEL_KEYS, 28),
                "method": method, "interval": {"low": low, "high": high},
                "history_count": 4, "history_std": 2, "missing_bleeding_ratio": 0}
    result = summarize_forecasts([
        record(28, "rf_personalized", 26, 30), record(35, "rf_personalized", 26, 30),
        record(28, "basic_stats", 28, 28),
    ])
    assert result["intervals"]["rf_personalized"] == {"samples": 2, "coverage_pct": 50, "mean_width_days": 4}
    assert result["intervals"]["basic_stats"] == {"samples": 1, "coverage_pct": 100, "mean_width_days": 0}
    assert summarize_forecasts([])["models"] == {}
