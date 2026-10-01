import json

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
