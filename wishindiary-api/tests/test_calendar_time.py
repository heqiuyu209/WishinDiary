from datetime import datetime, timezone

import pytest

from app.core import calendar_time
from app.core.database import transaction


@pytest.mark.parametrize("tz, allowed_day, rejected_day", [
    ("Asia/Shanghai", "2026-09-02", "2026-09-03"),
    ("America/Los_Angeles", "2026-09-01", "2026-09-02"),
])
def test_write_dates_use_account_day(client, auth_header, monkeypatch, tz, allowed_day, rejected_day):
    monkeypatch.setattr(calendar_time, "utc_now", lambda: datetime(2026, 9, 1, 16, 30, tzinfo=timezone.utc))
    user_id = client.get("/api/v1/auth/session").json()["user_id"]
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE users SET notification_timezone=%s WHERE user_id=%s", (tz, user_id))
    for path, key in [("log_start", "start_date"), ("daily_log", "log_date")]:
        assert client.post(f"/api/v1/{path}", json={key: allowed_day}).status_code == 200
        assert client.post(f"/api/v1/{path}", json={key: rejected_day}).status_code == 400
    assert client.post("/api/v1/log_end", json={"end_date": allowed_day}).status_code == 200
    assert client.post("/api/v1/log_end", json={"end_date": rejected_day}).status_code == 400
    cycle_id = client.get("/api/v1/stats").json()["cycles"][0]["cycle_id"]
    assert client.put(f"/api/v1/cycles/{cycle_id}", json={"end_date": allowed_day}).status_code == 200
    assert client.put(f"/api/v1/cycles/{cycle_id}", json={"start_date": rejected_day}).status_code == 400


def test_registration_uses_default_account_timezone(client, monkeypatch):
    monkeypatch.setattr(calendar_time, "utc_now", lambda: datetime(2026, 9, 1, 16, 30, tzinfo=timezone.utc))
    payload = {"username": "tz_register", "password": "password123",
               "period_start_dates": ["2026-08-05", "2026-09-02"]}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 200
    payload["username"] = "tz_future"
    payload["period_start_dates"][-1] = "2026-09-03"
    assert client.post("/api/v1/auth/register", json=payload).status_code == 422
