from datetime import date, timedelta


def _seed_cycle_and_log(client, auth_header):
    """写入一条周期和一条每日日志，作为导出/删除的验证数据。"""
    start = date(2026, 1, 1)
    end = start + timedelta(days=5)
    assert client.post("/api/v1/log_start", json={"start_date": start.isoformat()}, headers=auth_header).status_code == 200
    assert client.post("/api/v1/log_end", json={"end_date": end.isoformat()}, headers=auth_header).status_code == 200
    assert client.post(
        "/api/v1/daily_log",
        json={"log_date": "2026-01-02", "mood_level": 2, "journal_text": "压力有点大"},
        headers=auth_header,
    ).status_code == 200


def test_export_requires_auth(client):
    response = client.get("/api/v1/user/export")
    assert response.status_code == 401


def test_delete_requires_auth(client):
    response = client.delete("/api/v1/user/me")
    assert response.status_code == 401


def test_export_returns_all_user_data(client, auth_header):
    _seed_cycle_and_log(client, auth_header)
    response = client.get("/api/v1/user/export", headers=auth_header)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "exported_at" in payload
    assert payload["user"]["username"] == "test_user"
    assert len(payload["cycles"]) == 1
    assert payload["cycles"][0]["start_date"] == "2026-01-01"
    assert len(payload["daily_logs"]) == 1
    assert payload["daily_logs"][0]["journal_text"] == "压力有点大"
    # prediction_logs 结构存在（即使为空）
    assert "prediction_logs" in payload


def test_delete_user_cascades_data(client, auth_header):
    _seed_cycle_and_log(client, auth_header)

    # 删除前存在数据
    export_before = client.get("/api/v1/user/export", headers=auth_header).json()
    assert len(export_before["cycles"]) == 1
    assert len(export_before["daily_logs"]) == 1

    # 删除账号及级联数据
    response = client.delete("/api/v1/user/me", headers=auth_header)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 删除后该用户的数据应全部清空：再次访问导出应 401（Cookie 对应的用户已不存在，
    # 认证解析失败），或至少能确认无残留。这里用 db 层校验更稳定。
    from app.core.database import get_db_connection

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM users WHERE username = %s", ("test_user",))
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT COUNT(*) AS n FROM cycles WHERE user_id = 1")
            assert cur.fetchone()["n"] == 0
            cur.execute("SELECT COUNT(*) AS n FROM daily_logs WHERE user_id = 1")
            assert cur.fetchone()["n"] == 0
    finally:
        conn.close()
