from copy import deepcopy
from datetime import date, timedelta
import json

import pandas as pd
import pytest

from app.core.config import settings
from app.ml.forecast_evaluation import pipeline_fingerprint, run_forecast_backtest
from app.services.forecast_report_service import read_forecast_report


def _cycles():
    rows = []
    for user in range(1, 10):
        anchor = date(2024, 1, 1)
        for _ in range(14):
            rows.append({"user_id": user, "start_date": anchor, "cycle_length": 28, "bleeding_days": user})
            anchor += timedelta(days=28)
    return pd.DataFrame(rows)


class Tree:
    def __init__(self, value):
        self.value = value

    def predict(self, features):
        return [self.value] * len(features)


class RecordingModel:
    estimators_ = [Tree(27), Tree(29)]

    def fit(self, features, labels):
        self.features = features.copy()
        self.labels = list(labels)
        return self

    def predict(self, features):
        return [28] * len(features)


def _run(frame, **kwargs):
    return run_forecast_backtest(frame, cutoff="2024-09-01", calibration_cutoff="2024-06-01",
                                 n_splits=3, model_factory=RecordingModel, **kwargs)


@pytest.fixture(scope="module")
def temporal_report():
    return {"schema_version": 3, "pipeline_sha256": pipeline_fingerprint(),
            "dataset": {"source": "synthetic", "n_users": 9, "total_cycles": 126},
            "evaluation": _run(_cycles(), time_window_days=30)}


def _read(tmp_path, monkeypatch, report):
    monkeypatch.setattr(settings, "MODEL_PATH", tmp_path / "model.skops")
    (tmp_path / "forecast_evaluation_report.json").write_text(json.dumps(report), encoding="utf-8")
    return read_forecast_report()


def test_windows_partition_samples_at_exact_boundaries_and_preserve_empty_windows(temporal_report):
    evaluation = temporal_report["evaluation"]
    assert evaluation["time_windows"] == {
        "window_days": 30, "date_basis": "forecast_anchor", "last_candidate_date": "2024-12-30",
        "end_exclusive": "2025-01-29",
    }
    for protocol in evaluation["protocols"].values():
        windows = protocol["time_windows"]
        assert [window["samples"] for window in windows] == [9, 9, 9, 9, 9]
        assert windows[-2]["end_exclusive"] == windows[-1]["start"] == "2024-12-30"
        assert sum(window["samples"] for window in windows) == protocol["samples"]
        for buckets in protocol["groups"].values():
            assert sum(bucket["samples"] for bucket in buckets) == protocol["samples"]
            assert sum(bucket["interval_comparison"]["rf_personalized"]["comparison"]["samples"]
                       for bucket in buckets) == protocol["samples"]
    result = _run(_cycles(), time_window_days=7)
    empty = next(window for window in result["protocols"]["existing_users"]["time_windows"]
                 if not window["samples"])
    assert empty["models"] == {}
    assert empty["interval_comparison"]["rf_personalized"]["calibrated"] == {"samples": 0}


def test_later_drift_changes_coverage_without_refitting_models_or_radii(monkeypatch, temporal_report):
    frame = _cycles()
    frame.loc[frame.start_date >= date(2024, 10, 7), "cycle_length"] = 44
    fitted = []
    original_fit = RecordingModel.fit

    def record_fit(model, features, labels):
        fitted.append(list(labels))
        return original_fit(model, features, labels)

    monkeypatch.setattr(RecordingModel, "fit", record_fit)
    changed = _run(frame, time_window_days=30)
    assert len(fitted) == 4 and all(44 not in labels for labels in fitted)
    for name, before in temporal_report["evaluation"]["protocols"].items():
        after = changed["protocols"][name]
        assert after["calibration"]["methods"]["rf_personalized"]["fits"] == \
            before["calibration"]["methods"]["rf_personalized"]["fits"]
        assert after["time_windows"][0] == before["time_windows"][0]
        rf = after["time_windows"][1]["interval_comparison"]["rf_personalized"]
        assert rf["calibrated"]["coverage_pct"] == 0
        assert rf["comparison"]["original"]["samples"] == rf["comparison"]["calibrated"]["samples"] == 9
        assert after["time_windows"][1]["models"]["online_pipeline"]["mae"] > 0


@pytest.mark.parametrize("days", [0, 366, True, 1.5, "30"])
def test_invalid_window_size_fails_before_model_training(days):
    with pytest.raises(ValueError, match="window"):
        _run(_cycles(), time_window_days=days)


def test_excessive_windows_and_missing_calibration_fail_before_training():
    with pytest.raises(ValueError, match="60"):
        _run(_cycles(), time_window_days=1)
    with pytest.raises(ValueError, match="calibration"):
        run_forecast_backtest(_cycles(), time_window_days=30)


def test_schema_three_whitelists_aggregates_in_windows_and_groups(tmp_path, monkeypatch, temporal_report):
    report = deepcopy(temporal_report)
    window = report["evaluation"]["protocols"]["existing_users"]["time_windows"][0]
    window["records"] = [{"email": "never-return@example.com"}]
    window["interval_comparison"]["rf_personalized"]["residuals"] = [123]
    result = _read(tmp_path, monkeypatch, report)
    assert result["available"] and result["pipeline_matches_report"]
    assert result["protocols"]["existing_users"]["time_windows"][0]["models"]["online_pipeline"]["mae"] == 0
    assert result["protocols"]["existing_users"]["time_windows"][0]["interval_comparison"]["rf_personalized"]["calibrated"]["mean_width_days"] == 0
    assert "never-return" not in json.dumps(result) and "residuals" not in json.dumps(result)


def test_admin_recommends_future_verification_when_window_coverage_changes(client, auth_header, tmp_path, monkeypatch):
    report = {"schema_version": 3, "pipeline_sha256": pipeline_fingerprint(),
              "dataset": {"source": "synthetic", "n_users": 9, "total_cycles": 126}}
    frame = _cycles()
    frame.loc[frame.start_date >= date(2024, 10, 7), "cycle_length"] = 44
    report["evaluation"] = _run(frame, time_window_days=30)
    assert _read(tmp_path, monkeypatch, report)["available"]
    user = client.get("/api/v1/auth/session").json()["user_id"]
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", str(user))
    result = client.get("/api/v1/admin/research").json()
    assert result["forecast_evaluation"]["time_windows"]["window_days"] == 30
    assert any("4/5 个可评估时间窗" in item and "新时间段复核" in item for item in result["recommendations"])
    assert "test_user" not in json.dumps(result)


@pytest.mark.parametrize("invalid", [
    "days", "basis", "horizon", "last_date", "gap", "overlap", "early_start", "window_count",
    "sample_count", "paired_count", "unavailable", "coverage", "width", "missing_groups",
    "repeated_group", "group_count", "group_pair_count", "missing_window_protocol", "consistent_drop",
])
def test_invalid_temporal_partitions_fail_explicitly(tmp_path, monkeypatch, temporal_report, invalid):
    report = deepcopy(temporal_report)
    evaluation = report["evaluation"]
    protocol = evaluation["protocols"]["existing_users"]
    window = protocol["time_windows"][0]
    interval = window["interval_comparison"]["rf_personalized"]
    group = protocol["groups"]["history"][1]
    if invalid == "days":
        evaluation["time_windows"]["window_days"] = True
    elif invalid == "basis":
        evaluation["time_windows"]["date_basis"] = "target_completion"
    elif invalid == "horizon":
        evaluation["time_windows"]["end_exclusive"] = "2025-02-01"
    elif invalid == "last_date":
        evaluation["time_windows"]["last_candidate_date"] = "2024-08-31"
    elif invalid == "gap":
        protocol["time_windows"][1]["start"] = "2024-10-02"
    elif invalid == "overlap":
        protocol["time_windows"][1]["start"] = "2024-09-30"
    elif invalid == "early_start":
        window["start"] = "2024-08-31"
    elif invalid == "window_count":
        protocol["time_windows"].append(deepcopy(window))
    elif invalid == "sample_count":
        window["samples"] += 1
    elif invalid == "paired_count":
        interval["comparison"]["original"]["samples"] -= 1
    elif invalid == "unavailable":
        interval["unavailable_samples"] = 1
    elif invalid == "coverage":
        interval["comparison"]["calibrated"]["coverage_pct"] = 101
    elif invalid == "width":
        interval["calibrated"]["mean_width_days"] = -1
    elif invalid == "missing_groups":
        protocol["groups"]["history"].pop()
    elif invalid == "repeated_group":
        protocol["groups"]["history"][0]["label"] = group["label"]
    elif invalid == "group_count":
        group["samples"] += 1
    elif invalid == "group_pair_count":
        group["interval_comparison"]["rf_personalized"]["comparison"]["samples"] -= 1
    elif invalid == "missing_window_protocol":
        del protocol["time_windows"]
    elif invalid == "consistent_drop":
        # Each bucket remains internally valid, but one outcome disappeared from the partition.
        window["samples"] -= 1
        interval["test_samples"] -= 1
        interval["calibrated"]["samples"] -= 1
        interval["comparison"]["samples"] -= 1
        interval["comparison"]["original"]["samples"] -= 1
        interval["comparison"]["calibrated"]["samples"] -= 1
    assert _read(tmp_path, monkeypatch, report)["available"] is False
