import json
from copy import deepcopy

import pytest

from app.core.config import settings
from app.ml.forecast_evaluation import pipeline_fingerprint
from app.services.forecast_report_service import read_forecast_report


def _report():
    scores = {"samples": 2, "models": {
        "online_pipeline": {"mae": 0, "rmse": 0, "bias_days": 0, "hit_rate_within_3d": 100},
        "mean3": {"mae": 1.2}, "median3": {"mae": 1.3}, "ewma": {"mae": 1.4},
        "private_model": {"email": "never-return@example.com"},
    }, "intervals": {"rf_personalized": {"samples": 2, "coverage_pct": 50, "mean_width_days": 0}},
        "groups": {"history": [
            {"label": "0–3 条", "samples": 0, "models": {"online_pipeline": {"mae": 123}}},
            {"label": "4–7 条", "samples": 2, "models": {"online_pipeline": {"mae": 0}}},
            {"label": "never-return@example.com", "samples": 1, "models": {}},
        ]}}
    return {"schema_version": 1, "pipeline_sha256": pipeline_fingerprint(),
            "metadata": {"git_commit": "a" * 40, "generated_at": "2026-10-01T00:00:00+00:00"},
            "dataset": {"source": "synthetic", "total_cycles": 20, "n_users": 2,
                        "records": [{"email": "never-return@example.com"}]},
            "evaluation": {"cutoff": "2024-05-01",
                           "protocols": {"existing_users": scores, "unseen_users": scores}},
            "raw_records": [{"email": "never-return@example.com"}]}


def _write(tmp_path, monkeypatch, report):
    monkeypatch.setattr(settings, "MODEL_PATH", tmp_path / "model.skops")
    path = tmp_path / "forecast_evaluation_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_report_whitelists_aggregates_and_preserves_zero_and_empty_groups(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, _report())
    result = read_forecast_report()
    assert result["available"] and result["pipeline_matches_report"]
    existing = result["protocols"]["existing_users"]
    assert existing["models"]["online_pipeline"]["mae"] == 0
    assert existing["intervals"]["rf_personalized"]["mean_width_days"] == 0
    assert existing["groups"]["history"][0]["models"] == {}
    assert "never-return" not in json.dumps(result)
    assert "raw_records" not in result


def test_code_mismatch_is_explicit(tmp_path, monkeypatch):
    report = _report()
    report["pipeline_sha256"] = "0" * 64
    _write(tmp_path, monkeypatch, report)
    assert read_forecast_report()["pipeline_matches_report"] is False


@pytest.mark.parametrize("invalid", ["json", "nan", "oversize", "negative_count", "boolean_schema"])
def test_invalid_reports_have_explicit_unavailable_state(tmp_path, monkeypatch, invalid):
    report = _report()
    if invalid == "negative_count":
        report["dataset"]["total_cycles"] = -1
    if invalid == "boolean_schema":
        report["schema_version"] = True
    path = _write(tmp_path, monkeypatch, report)
    if invalid == "json":
        path.write_text("not JSON")
    elif invalid == "nan":
        path.write_text(path.read_text().replace('"mae": 0', '"mae": NaN'))
    elif invalid == "oversize":
        path.write_text(" " * 1_000_001)
    result = read_forecast_report()
    assert result["available"] is False
    assert "无效" in result["message"]


def test_admin_summary_recommends_independent_interval_calibration(client, auth_header, tmp_path, monkeypatch):
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", str(user_id))
    _write(tmp_path, monkeypatch, _report())
    response = client.get("/api/v1/admin/research")
    assert response.status_code == 200
    result = response.json()
    assert result["forecast_evaluation"]["available"] is True
    assert any("50.00%" in recommendation and "校准" in recommendation for recommendation in result["recommendations"])
    assert any("合成" in recommendation for recommendation in result["recommendations"])
    assert "never-return" not in response.text
    assert "test_user" not in response.text
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", "")
    assert client.get("/api/v1/admin/research").status_code == 403


def _calibrated_report():
    report = deepcopy(_report())
    report["schema_version"] = 2
    evaluation = report["evaluation"]
    evaluation["training_labels_available_through"] = "2024-03-28"
    evaluation["calibration"] = {
        "method": "absolute_residual_split", "cutoff": "2024-04-01",
        "labels_available_through": "2024-04-28", "candidate_samples": 9,
        "target_coverage_pct": 90,
    }
    for name in ("existing_users", "unseen_users"):
        value = deepcopy(evaluation["protocols"][name])
        value["n_splits"] = 1
        value["calibration"] = {"target_coverage_pct": 90, "methods": {
            "rf_personalized": {
                "fits": [{"samples": 9, "rank": 9, "available": True, "radius_days": 0,
                          "email": "never-return@example.com"}],
                "test_samples": 2, "unavailable_samples": 0,
                "calibrated": {"samples": 2, "coverage_pct": 100, "mean_width_days": 0},
                "comparison": {
                    "samples": 2,
                    "original": {"samples": 2, "coverage_pct": 50, "mean_width_days": 0},
                    "calibrated": {"samples": 2, "coverage_pct": 100, "mean_width_days": 0},
                    "records": [{"email": "never-return@example.com"}],
                },
            },
            "basic_stats": {
                "fits": [{"samples": 0, "rank": 1, "available": False}],
                "test_samples": 0, "unavailable_samples": 0,
                "calibrated": {"samples": 0, "coverage_pct": 100, "mean_width_days": 99},
                "comparison": {"samples": 0, "original": {"samples": 0}, "calibrated": {"samples": 0}},
            },
        }}
        evaluation["protocols"][name] = value
    return report


def test_schema_two_whitelists_calibration_and_preserves_zero_radius(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, _calibrated_report())
    result = read_forecast_report()
    assert result["available"] and result["pipeline_matches_report"]
    assert result["calibration"]["cutoff"] == "2024-04-01"
    methods = result["protocols"]["existing_users"]["calibration"]["methods"]
    assert methods["rf_personalized"]["fits"][0]["radius_days"] == 0
    assert methods["rf_personalized"]["comparison"]["calibrated"]["mean_width_days"] == 0
    assert methods["basic_stats"]["calibrated"] == {"samples": 0}
    assert "never-return" not in json.dumps(result)


@pytest.mark.parametrize("invalid", [
    "training_after_calibration", "calibration_after_test", "unknown_calibration_labels", "method",
    "paired_samples", "target", "radius", "available", "paths", "percentage", "folds",
])
def test_invalid_calibration_report_fails_explicitly(tmp_path, monkeypatch, invalid):
    report = _calibrated_report()
    evaluation = report["evaluation"]
    calibrated = evaluation["protocols"]["existing_users"]["calibration"]
    rf = calibrated["methods"]["rf_personalized"]
    if invalid == "training_after_calibration":
        evaluation["training_labels_available_through"] = "2024-04-02"
    elif invalid == "calibration_after_test":
        evaluation["calibration"]["labels_available_through"] = "2024-05-02"
    elif invalid == "unknown_calibration_labels":
        evaluation["calibration"]["labels_available_through"] = None
    elif invalid == "method":
        evaluation["calibration"]["method"] = "never-return@example.com"
    elif invalid == "paired_samples":
        rf["comparison"]["original"]["samples"] = 1
    elif invalid == "target":
        calibrated["target_coverage_pct"] = 95
    elif invalid == "radius":
        rf["fits"][0]["radius_days"] = -1
    elif invalid == "available":
        rf["fits"][0]["available"] = False
    elif invalid == "paths":
        rf["test_samples"] = 3
    elif invalid == "percentage":
        rf["comparison"]["calibrated"]["coverage_pct"] = 101
    elif invalid == "folds":
        rf["fits"] = rf["fits"] * 101
    _write(tmp_path, monkeypatch, report)
    assert read_forecast_report()["available"] is False


def test_empty_calibration_segment_keeps_point_scores_but_no_finite_intervals(tmp_path, monkeypatch):
    report = _calibrated_report()
    report["evaluation"]["calibration"].update(candidate_samples=0, labels_available_through=None)
    for value in report["evaluation"]["protocols"].values():
        rf = value["calibration"]["methods"]["rf_personalized"]
        rf.update(fits=[{"samples": 0, "rank": 1, "available": False}], unavailable_samples=2,
                  calibrated={"samples": 0},
                  comparison={"samples": 0, "original": {"samples": 0}, "calibrated": {"samples": 0}})
    _write(tmp_path, monkeypatch, report)
    result = read_forecast_report()
    assert result["available"] is True
    assert result["protocols"]["existing_users"]["models"]["online_pipeline"]["mae"] == 0
    assert result["protocols"]["existing_users"]["calibration"]["methods"]["rf_personalized"]["unavailable_samples"] == 2


def test_admin_calibration_recommendations_do_not_call_the_target_a_guarantee(client, auth_header, tmp_path, monkeypatch):
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", str(user_id))
    report = _calibrated_report()
    report["evaluation"]["protocols"]["existing_users"]["calibration"]["methods"]["rf_personalized"]["calibrated"]["coverage_pct"] = 50
    _write(tmp_path, monkeypatch, report)
    result = client.get("/api/v1/admin/research").json()
    assert result["forecast_evaluation"]["calibration"]["target_coverage_pct"] == 90
    assert any("低于实验目标" in item for item in result["recommendations"])
    assert any("独立时间校准实验" in item for item in result["recommendations"])
    assert not any("优先建立独立时间校准段" in item for item in result["recommendations"])
    assert "never-return" not in json.dumps(result)
