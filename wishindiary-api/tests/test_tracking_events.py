from datetime import datetime, timezone

from app.core.database import transaction
from app.repositories import cycle_research_repository as repository


def test_cycle_geometry_keeps_pre_edit_versions(client, auth_header, monkeypatch):
    monkeypatch.setattr(repository, "utc_now", lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert client.post("/api/v1/log_start", json={"start_date": "2024-01-01"}).status_code == 200
    cycle = client.get("/api/v1/stats").json()["cycles"][0]
    monkeypatch.setattr(repository, "utc_now", lambda: datetime(2026, 9, 2, tzinfo=timezone.utc))
    assert client.put(f"/api/v1/cycles/{cycle['cycle_id']}", json={"start_date": "2024-01-02"}).status_code == 200
    revisions = client.get("/api/v1/user/export").json()["cycle_revisions"]
    assert [row["start_date"] for row in revisions] == ["2024-01-01", "2024-01-02"]
    assert client.delete(f"/api/v1/cycles/{cycle['cycle_id']}").status_code == 200
    assert client.get("/api/v1/user/export").json()["cycle_revisions"] == []
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cycle_history_reset_at FROM users")
            assert cursor.fetchone()["cycle_history_reset_at"] is not None


def test_tracking_confirmations_validate_ownership_and_actual_sequence(client, auth_header):
    for start in ["2024-01-01", "2024-03-01"]:
        assert client.post("/api/v1/log_start", json={"start_date": start}).status_code == 200
    first, latest = client.get("/api/v1/stats").json()["cycles"]
    def confirm(cycle, kind, day="2024-03-02"):
        return client.post(f"/api/v1/cycles/{cycle}/tracking", json={"kind": kind, "as_of_date": day})
    assert confirm(first['cycle_id'], "no_onset").status_code == 400
    assert confirm(latest['cycle_id'], "no_onset", "2099-01-01").status_code == 400
    assert confirm(latest['cycle_id'], "no_onset", "2024-02-01").status_code == 400
    assert confirm(9999, "no_onset").status_code == 404
    assert confirm(latest['cycle_id'], "true_long_interval").status_code == 400
    assert confirm(first['cycle_id'], "missed_tracking").status_code == 200
    assert confirm(first['cycle_id'], "true_long_interval").status_code == 200
    assert confirm(latest['cycle_id'], "no_onset").status_code == 200
    assert client.get("/api/v1/stats").json()["cycles"][0]["tracking_kind"] == "true_long_interval"
    events = client.get("/api/v1/user/export").json()["cycle_tracking_events"]
    assert len(events) == 3 and events[-1]["anchor_start_date"] == "2024-03-01"
    # Editing the anchor invalidates old confirmations, without rewriting history.
    assert client.put(f"/api/v1/cycles/{latest['cycle_id']}", json={"start_date": "2024-03-02"}).status_code == 200
    assert client.get("/api/v1/stats").json()["cycles"][-1]["tracking_kind"] is None
    assert client.delete("/api/v1/user/me").status_code == 200
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM cycle_tracking_events")
            assert cursor.fetchone()["n"] == 0
