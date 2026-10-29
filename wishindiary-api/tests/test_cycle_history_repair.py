import json
from datetime import date

import pytest

from app.core.database import transaction
from scripts.repair_cycle_history import plan_repairs, repair_history


def test_repair_plan_preserves_real_end_and_does_not_guess_missing_end():
    rows = [
        {"cycle_id": 1, "user_id": 1, "start_date": date(2024, 1, 1),
         "end_date": date(2024, 1, 5), "cycle_length": None, "bleeding_days": 5},
        {"cycle_id": 2, "user_id": 1, "start_date": date(2024, 1, 29),
         "end_date": date(2024, 2, 26), "cycle_length": 28, "bleeding_days": 5},
        {"cycle_id": 3, "user_id": 1, "start_date": date(2024, 2, 26),
         "end_date": None, "cycle_length": None, "bleeding_days": None},
    ]
    repairs = plan_repairs(rows)
    assert repairs[0]["after"] == {
        "cycle_length": 28, "end_date": date(2024, 1, 5), "bleeding_days": 5,
    }
    assert repairs[1]["after"] == {"cycle_length": 28, "end_date": None, "bleeding_days": None}
    assert rows[1]["end_date"] == date(2024, 2, 26)


def test_dry_run_and_apply_with_private_recovery_copy(client, auth_header, tmp_path):
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO cycles (user_id,start_date,end_date,cycle_length,bleeding_days) "
                           "VALUES (%s,'2024-01-01','2024-01-29',28,5),(%s,'2024-01-29',NULL,NULL,NULL)",
                           (user_id, user_id))
    assert repair_history()["records_to_repair"] == 1
    assert client.get("/api/v1/stats").json()["cycles"][0]["end_date"] == "2024-01-29"
    with pytest.raises(ValueError, match="requires"):
        repair_history(apply=True)
    backup = tmp_path / "recovery.json"
    assert repair_history(apply=True, backup=backup)["records_to_repair"] == 1
    assert json.loads(backup.read_text())[0]["before"]["end_date"] == "2024-01-29"
    assert backup.stat().st_mode & 0o777 == 0o600
    first = client.get("/api/v1/stats").json()["cycles"][0]
    assert first["end_date"] is None
    assert first["cycle_length"] == 28
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT end_date,source FROM cycle_revisions WHERE user_id=%s ORDER BY start_date", (user_id,))
            revisions = cursor.fetchall()
    assert len(revisions) == 2
    assert all(row["source"] == "repair_snapshot" for row in revisions)
    assert revisions[0]["end_date"] is None
    assert repair_history()["records_to_repair"] == 0
    assert client.post("/api/v1/log_end", json={"end_date": "2024-02-02"}).status_code == 200


def test_retention_resets_research_history_and_recalculates_remaining_cycle(client, auth_header, monkeypatch):
    from app.core import database
    from scripts import cleanup_expired_data

    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    assert client.post("/api/v1/log_start", json={"start_date": "2024-01-01"}).status_code == 200
    assert client.post("/api/v1/log_start", json={"start_date": "2024-01-29"}).status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE cycles SET created_at='2000-01-01' WHERE user_id=%s AND start_date='2024-01-29'", (user_id,))
    monkeypatch.setattr(cleanup_expired_data, "_connect", database.get_db_connection)
    monkeypatch.setattr("sys.argv", ["cleanup_expired_data.py", "--days", "365"])
    assert cleanup_expired_data.main() == 0
    assert len(client.get("/api/v1/stats").json()["cycles"]) == 2
    monkeypatch.setattr("sys.argv", ["cleanup_expired_data.py", "--apply", "--days", "365"])
    assert cleanup_expired_data.main() == 0
    cycles = client.get("/api/v1/stats").json()["cycles"]
    assert len(cycles) == 1
    assert cycles[0]["cycle_length"] is None
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cycle_history_reset_at FROM users WHERE user_id=%s", (user_id,))
            assert cursor.fetchone()["cycle_history_reset_at"] is not None
            cursor.execute("SELECT COUNT(*) AS n FROM cycle_revisions WHERE user_id=%s", (user_id,))
            assert cursor.fetchone()["n"] == 1


def test_daily_only_retention_invalidates_private_research_snapshot(client, auth_header, monkeypatch):
    from app.core import database
    from app.core.research_policy import POLICY_VERSION
    from app.services.research_dataset_service import read_authorized_database, validate_snapshot
    from scripts import cleanup_expired_data

    user_id = client.get('/api/v1/auth/session').json()['user_id']
    assert client.put('/api/v1/research/participation', json={'participate': True,
        'policy_version': POLICY_VERSION, 'adult_confirmed': True}).status_code == 200
    assert client.post('/api/v1/daily_log', json={'log_date': '2024-01-01', 'stress_level': 2}).status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE daily_logs SET created_at='2000-01-01' WHERE user_id=%s", (user_id,))
    snapshot = read_authorized_database()
    monkeypatch.setattr(cleanup_expired_data, '_connect', database.get_db_connection)
    monkeypatch.setattr('sys.argv', ['cleanup_expired_data.py', '--days', '365'])
    assert cleanup_expired_data.main() == 0
    assert validate_snapshot(snapshot)['daily_log_revisions']
    monkeypatch.setattr('sys.argv', ['cleanup_expired_data.py', '--apply', '--days', '365'])
    assert cleanup_expired_data.main() == 0
    with pytest.raises(ValueError, match='consent changed'):
        validate_snapshot(snapshot)
