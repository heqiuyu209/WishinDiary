import json
from datetime import datetime, timezone

from app.core.database import transaction
from app.repositories import daily_log_repository as repository


def test_unknown_and_explicit_absence_are_distinct(client, auth_header):
    for payload in [{"log_date": "2024-01-01"}, {"log_date": "2024-01-02", "is_exercise": False,
                    "is_intercourse": False, "sleep_duration_minutes": 0, "stress_level": 0,
                    "symptom_levels": {"headache": 0}}]:
        assert client.post("/api/v1/daily_log", json=payload).status_code == 200
    unknown = client.get("/api/v1/daily_log?date=2024-01-01").json()["log"]
    absent = client.get("/api/v1/daily_log?date=2024-01-02").json()["log"]
    assert unknown["is_exercise"] is None and unknown["sleep_duration_minutes"] is None
    assert unknown["symptom_levels"]["headache"] is None
    assert absent["is_exercise"] is False and absent["exercise_minutes"] == 0
    assert absent["sleep_duration_minutes"] == absent["stress_level"] == 0
    assert absent["symptom_levels"]["headache"] == 0
    assert absent["symptom_levels"]["fatigue"] is None
    assert client.get("/api/v1/stats").status_code == 200


def test_revision_cutoff_excludes_future_backfill_and_edits(client, auth_header, monkeypatch):
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    early = datetime(2026, 9, 1, 1, tzinfo=timezone.utc)
    late = datetime(2026, 9, 3, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(repository, "utc_now", lambda: early)
    assert client.post("/api/v1/daily_log", json={"log_date": "2024-01-01",
        "sleep_duration_minutes": 480, "stress_level": 1, "journal_text": "private fixture",
        "is_intercourse": True}).status_code == 200
    monkeypatch.setattr(repository, "utc_now", lambda: late)
    assert client.put("/api/v1/daily_log", json={"log_date": "2024-01-01",
        "sleep_duration_minutes": 300, "stress_level": 3}).status_code == 200
    assert client.post("/api/v1/daily_log", json={"log_date": "2024-01-02",
        "exercise_minutes": 60, "is_exercise": True, "exercise_intensity": 3}).status_code == 200
    log = client.get("/api/v1/daily_log?date=2024-01-01").json()["log"]
    assert log["recorded_at"] == early.isoformat() and log["updated_at"] == late.isoformat()
    with transaction() as connection:
        with connection.cursor() as cursor:
            assert repository.get_daily_revisions_as_of(cursor, user_id, early) == []
            rows = repository.get_daily_revisions_as_of(cursor, user_id, datetime(2026, 9, 2, tzinfo=timezone.utc))
    assert len(rows) == 1
    assert json.loads(rows[0]["payload"])["sleep_duration_minutes"] == 480
    assert "private fixture" not in rows[0]["payload"] and "intercourse" not in rows[0]["payload"]
    exported = client.get("/api/v1/user/export").json()
    assert len(exported["daily_log_revisions"]) == 3
    assert client.delete("/api/v1/daily_log?date=2024-01-01").status_code == 200
    assert len(client.get("/api/v1/user/export").json()["daily_log_revisions"]) == 1
    assert client.delete("/api/v1/user/me").status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM daily_log_revisions")
            assert cursor.fetchone()["n"] == 0


def test_lifestyle_validation_conflicts_and_limits(client, auth_header):
    for fields in [{"stress_level": 4}, {"exercise_intensity": 4}, {"sleep_start_minutes": 1440},
                   {"is_exercise": False, "exercise_minutes": 60}, {"symptom_levels": {"fatigue": True}}]:
        assert client.post("/api/v1/daily_log", json={"log_date": "2024-01-01", **fields}).status_code == 422
