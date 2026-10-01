from datetime import date, timedelta

import pandas as pd
import pytest

from app.ml import forecast_evaluation as evaluation
from app.ml.interval_calibration import (
    apply_interval_calibration, fit_interval_calibrators, summarize_interval_calibration,
)


def _row(error=0, method="rf_personalized", point=28, interval=None):
    return {"actual": point + error, "predictions": {"online_pipeline": point},
            "method": method, "interval": interval}


@pytest.mark.parametrize("count,rank,radius", [(9, 9, 8), (19, 18, 17)])
def test_finite_sample_rank_uses_an_observed_error_without_interpolation(count, rank, radius):
    fit = fit_interval_calibrators([_row(error) for error in range(count)])["rf_personalized"]
    assert fit == {"samples": count, "rank": rank, "available": True, "radius_days": radius}


def test_decimal_probability_does_not_round_an_integer_rank_up():
    fit = fit_interval_calibrators([_row(error) for error in range(99)], 0.14)["rf_personalized"]
    assert fit["rank"] == 14 and fit["radius_days"] == 13


def test_insufficient_paths_are_not_pooled_or_given_a_capped_quantile():
    rows = [_row(error) for error in range(9)] + [_row(100, "basic_stats") for _ in range(8)]
    fits = fit_interval_calibrators(rows)
    assert fits["rf_personalized"]["available"] is True
    assert fits["basic_stats"] == {"samples": 8, "rank": 9, "available": False}
    assert apply_interval_calibration([_row(100, "basic_stats")], fits)[0]["calibrated_interval"] is None
    assert fit_interval_calibrators([])["rf_personalized"]["available"] is False


@pytest.mark.parametrize("coverage", [0, 1, -0.1, float("nan"), float("inf"), True])
def test_invalid_coverage_is_rejected(coverage):
    with pytest.raises(ValueError, match="coverage"):
        fit_interval_calibrators([], coverage)


def test_nonfinite_calibration_errors_are_rejected():
    with pytest.raises(ValueError, match="finite"):
        fit_interval_calibrators([_row(float("nan"))])


def test_frozen_radius_does_not_read_test_outcomes_or_clip_to_point_limits():
    fits = fit_interval_calibrators([_row(20) for _ in range(9)])
    original = _row(0, point=44)
    changed = {**original, "actual": 300}
    results = apply_interval_calibration([original, changed], fits)
    assert [row["calibrated_interval"] for row in results] == [{"low": 24, "high": 64}] * 2
    assert "calibrated_interval" not in original


def test_original_and_calibrated_coverage_use_identical_paired_test_samples():
    fits = fit_interval_calibrators([_row(4) for _ in range(9)])
    rows = apply_interval_calibration([
        _row(0, interval={"low": 27, "high": 29}),
        _row(4, interval={"low": 27, "high": 29}),
        _row(100),  # No original interval: excluded from both paired metrics.
        _row(0, "basic_stats", interval={"low": 28, "high": 28}),
    ], fits)
    result = summarize_interval_calibration(rows, [fits], 0.9)
    rf = result["methods"]["rf_personalized"]
    assert rf["test_samples"] == rf["calibrated"]["samples"] == 3
    assert rf["comparison"] == {
        "samples": 2,
        "original": {"samples": 2, "coverage_pct": 50, "mean_width_days": 2},
        "calibrated": {"samples": 2, "coverage_pct": 100, "mean_width_days": 8},
    }
    basic = result["methods"]["basic_stats"]
    assert basic["unavailable_samples"] == 1 and basic["comparison"]["samples"] == 0
    assert basic["calibrated"] == {"samples": 0}


def _cycles():
    rows = []
    for user_id in range(1, 10):
        anchor = date(2024, 1, 1)
        for _ in range(14):
            rows.append({"user_id": user_id, "start_date": anchor,
                         "cycle_length": 28, "bleeding_days": user_id})
            anchor += timedelta(days=28)
    return pd.DataFrame(rows)


class RecordingModel:
    def fit(self, features, labels):
        self.features = features.copy()
        self.labels = list(labels)
        self.users = set(features.lag_1_bleeding)
        return self

    def predict(self, features):
        return [28] * len(features)


def _run(frame, **kwargs):
    return evaluation.run_forecast_backtest(
        frame, cutoff="2024-09-01", calibration_cutoff="2024-06-01",
        n_splits=3, model_factory=RecordingModel, **kwargs,
    )


def test_training_and_calibration_exclude_the_same_held_out_test_users(monkeypatch):
    original_predict = evaluation.predict_case
    original_fit = evaluation.fit_interval_calibrators
    original_apply = evaluation.apply_interval_calibration
    observed = []

    def predict(case, predictor):
        return {**original_predict(case, predictor), "test_user": case.user_id,
                "training_users": predictor.model.users}

    def fit(rows, coverage):
        if rows:
            users = {row["test_user"] for row in rows}
            assert users == rows[0]["training_users"]
            observed.append(users)
        return original_fit(rows, coverage)

    def apply(rows, fits):
        if len(observed) > 1:
            assert {row["test_user"] for row in rows}.isdisjoint(observed[-1])
        return original_apply(rows, fits)

    monkeypatch.setattr(evaluation, "predict_case", predict)
    monkeypatch.setattr(evaluation, "fit_interval_calibrators", fit)
    monkeypatch.setattr(evaluation, "apply_interval_calibration", apply)
    result = _run(_cycles())
    assert len(observed) == 4
    assert len(observed[0]) == 9 and all(len(users) == 6 for users in observed[1:])
    assert result["training_labels_available_through"] <= result["calibration"]["cutoff"]
    assert result["calibration"]["labels_available_through"] <= result["cutoff"]
    assert "test_user" not in str(result) and "training_users" not in str(result)


def test_future_test_labels_cannot_change_fitted_radii():
    frame = _cycles()
    before = _run(frame)
    frame.loc[frame.start_date >= date(2024, 9, 1), "cycle_length"] = 44
    after = _run(frame)
    for name in before["protocols"]:
        for method in ("rf_personalized", "basic_stats"):
            assert before["protocols"][name]["calibration"]["methods"][method]["fits"] == \
                after["protocols"][name]["calibration"]["methods"][method]["fits"]
    assert before["protocols"]["existing_users"]["models"]["online_pipeline"]["mae"] == 0
    assert after["protocols"]["existing_users"]["models"]["online_pipeline"]["mae"] > 0


def test_calibration_label_must_finish_before_the_test_cutoff():
    frame = _cycles()
    # July starts are in calibration, but their modified labels finish in September.
    frame.loc[pd.to_datetime(frame.start_date).dt.month == 7, "cycle_length"] = 60
    result = _run(frame)
    assert result["calibration"]["candidate_samples"] == 9
    assert result["calibration"]["labels_available_through"] <= result["cutoff"]
    fit = result["protocols"]["existing_users"]["calibration"]["methods"]["rf_personalized"]["fits"][0]
    assert fit["samples"] == 9 and fit["radius_days"] == 0
    unseen = result["protocols"]["unseen_users"]["calibration"]["methods"]["rf_personalized"]
    assert unseen["unavailable_samples"] == unseen["test_samples"]


@pytest.mark.parametrize("kwargs", [
    {"calibration_fraction": -0.1}, {"calibration_fraction": 0.8},
    {"calibration_cutoff": "2024-09-01"}, {"calibration_cutoff": "2024-09-02"},
    {"calibration_cutoff": "2024-06-01T12:00:00"}, {"cutoff": "2024-09-01T00:00:00+00:00"},
])
def test_invalid_time_segments_fail_before_training(kwargs):
    options = {"cutoff": "2024-09-01", "calibration_cutoff": "2024-06-01", **kwargs}
    with pytest.raises(ValueError, match="cutoff|fraction"):
        evaluation.run_forecast_backtest(_cycles(), model_factory=RecordingModel, **options)
