"""B1 数据完整性测试：log_start 禁止落在已闭合经期记录区间内。"""

USERNAME = "overlap_user"
PASSWORD = "password123"


def _login(client):
    payload = {"username": USERNAME, "password": PASSWORD}
    client.post("/api/v1/auth/register", json=payload)
    resp = client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 200, resp.text


def test_log_start_rejects_start_inside_closed_cycle(client):
    """已闭合周期 [2026-08-01, 2026-08-05] 内再开始新周期 → 400 重叠。"""
    _login(client)
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-01"}
    ).status_code == 200
    assert client.post(
        "/api/v1/log_end", json={"end_date": "2026-08-05"}
    ).status_code == 200

    res = client.post("/api/v1/log_start", json={"start_date": "2026-08-03"})
    assert res.status_code == 400
    assert "重叠" in res.json()["error"]["message"]


def test_log_start_rejects_on_closed_cycle_end_date(client):
    """开始日期恰好等于已闭合周期的结束日 → 同样视为重叠，拒绝。"""
    _login(client)
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-01"}
    ).status_code == 200
    assert client.post(
        "/api/v1/log_end", json={"end_date": "2026-08-05"}
    ).status_code == 200

    res = client.post("/api/v1/log_start", json={"start_date": "2026-08-05"})
    assert res.status_code == 400
    assert "重叠" in res.json()["error"]["message"]


def test_log_start_allows_start_after_closed_cycle(client):
    """闭合周期结束后的相邻新周期 → 200，且不影响后续闭环。"""
    _login(client)
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-01"}
    ).status_code == 200
    assert client.post(
        "/api/v1/log_end", json={"end_date": "2026-08-05"}
    ).status_code == 200

    res = client.post("/api/v1/log_start", json={"start_date": "2026-08-07"})
    assert res.status_code == 200, res.text

    # 新周期可正常闭合：不破坏原有闭环逻辑
    res2 = client.post("/api/v1/log_end", json={"end_date": "2026-08-10"})
    assert res2.status_code == 200, res2.text
