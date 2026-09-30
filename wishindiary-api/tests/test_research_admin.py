import hashlib
import json

from app.core.config import settings
from app.services.research_service import read_evaluation_report


def test_anonymous_cannot_access_research(client):
    assert client.get("/api/v1/admin/research").status_code == 401


def test_regular_user_cannot_access_research(client, auth_header, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", "")
    assert client.get("/api/v1/admin/research").status_code == 403
    assert client.get("/api/v1/auth/session").json()["is_admin"] is False


def test_admin_receives_only_aggregate_data_and_baseline_guidance(client, auth_header, monkeypatch, tmp_path):
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", str(user_id))
    model = tmp_path / "model.skops"
    model.write_bytes(b"fixture model")
    monkeypatch.setattr(settings, "MODEL_PATH", model)
    report = {"metadata": {"model_version": "test-rf"},
              "dataset": {"source": "synthetic", "total_samples": 210},
              "group_kfold": {"mae": 2.1, "baseline_mean3_mae": 1.8},
              "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
              "private_email": "never-return@example.com"}
    (tmp_path / "model_evaluation_report.json").write_text(json.dumps(report))
    assert client.get("/api/v1/auth/session").json()["is_admin"] is True
    response = client.get("/api/v1/admin/research")
    assert response.status_code == 200
    result = response.json()
    assert result["data"]["users"] == 1
    assert result["data"]["history_distribution"][0]["count"] == 1
    assert result["evaluation"]["model_matches_report"] is True
    assert any("尚未优于" in text for text in result["recommendations"])
    assert "test_user" not in response.text
    assert "never-return" not in response.text


def test_invalid_or_missing_report_has_explicit_state(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "MODEL_PATH", tmp_path / "model.skops")
    assert read_evaluation_report()["available"] is False
    (tmp_path / "model_evaluation_report.json").write_text("not JSON")
    assert read_evaluation_report()["available"] is False
