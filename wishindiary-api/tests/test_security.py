"""安全相关测试：登录响应不泄露 JWT、用户 A/B 数据隔离、越权修改/删除、CSRF 防护。"""

from fastapi.testclient import TestClient
from app.main import app


def _register_and_login(client: TestClient, username: str, password: str = "password123"):
    register = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert register.status_code == 200, register.text
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return login


def test_login_response_does_not_expose_jwt(client):
    """P0 安全：登录响应体不再携带 access_token/token_type。"""
    response = _register_and_login(client, "jwt_probe_user")
    body = response.json()
    assert "access_token" not in body
    assert "token_type" not in body
    # HttpOnly Cookie 依然由 Set-Cookie 下发
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token=" in set_cookie
    assert "HttpOnly" in set_cookie


def test_user_data_is_isolated_between_accounts():
    """P0 安全：A 用户的数据对 B 用户不可见（A/B 数据隔离）。"""
    client_a = TestClient(app)
    client_b = TestClient(app)
    _register_and_login(client_a, "alice")
    _register_and_login(client_b, "bob")

    # Alice 记录一条周期和一条每日日志
    assert client_a.post("/api/v1/log_start", json={"start_date": "2026-07-01"}).status_code == 200
    assert client_a.post(
        "/api/v1/daily_log",
        json={"log_date": "2026-07-03", "mood_level": 2},
    ).status_code == 200

    # Bob 的 stats 应为空
    bob_stats = client_b.get("/api/v1/stats").json()
    assert bob_stats["cycles"] == []
    assert bob_stats["recent_logs"] == []

    # Bob 的 report 不应包含 Alice 的任何周期
    bob_report = client_b.get("/api/v1/report")
    assert bob_report.status_code == 200
    report_text = bob_report.text
    assert "2026-07-01" not in report_text
    assert "2026-07-03" not in report_text


def test_cross_user_modify_and_delete_are_denied():
    """P0 安全：越权修改与越权删除必须被拒绝（返回 404）。"""
    client_a = TestClient(app)
    client_b = TestClient(app)
    _register_and_login(client_a, "carol")
    _register_and_login(client_b, "dave")

    assert client_a.post("/api/v1/log_start", json={"start_date": "2026-08-01"}).status_code == 200
    cycles = client_a.get("/api/v1/stats").json()["cycles"]
    cycle_id = next(c["cycle_id"] for c in cycles if c["start_date"] == "2026-08-01")

    # Dave 尝试修改 Carol 的周期
    res = client_b.put(f"/api/v1/cycles/{cycle_id}", json={"end_date": "2026-08-05"})
    assert res.status_code == 404

    # Dave 尝试删除 Carol 的周期
    res = client_b.delete(f"/api/v1/cycles/{cycle_id}")
    assert res.status_code == 404

    # 删除未生效
    remaining = client_a.get("/api/v1/stats").json()["cycles"]
    assert any(c["cycle_id"] == cycle_id for c in remaining)


def test_csrf_rejects_untrusted_origin_on_mutation(client):
    """P0 安全：携带认证 Cookie 的非安全方法，若 Origin 不在白名单应被拒。"""
    _register_and_login(client, "csrf_user")

    # 携带合法 cookie，但伪造恶意 Origin
    headers = {"Origin": "https://evil.example.com"}
    res = client.post(
        "/api/v1/log_start",
        json={"start_date": "2026-09-01"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "CSRF" in res.json()["error"]["message"]


def test_csrf_allows_same_origin(client):
    """P0 安全：同源 Origin 的非安全请求应放行。"""
    _register_and_login(client, "same_origin_user")
    headers = {"Origin": "http://testserver"}  # TestClient 默认 Host
    res = client.post(
        "/api/v1/log_start",
        json={"start_date": "2026-08-01"},
        headers=headers,
    )
    assert res.status_code == 200


def test_csrf_allows_missing_origin_for_non_browser_client(client):
    """P0 安全：无 Origin/Referer 的非浏览器客户端（curl/脚本）应放行。"""
    _register_and_login(client, "curl_user")
    res = client.post("/api/v1/log_start", json={"start_date": "2026-08-02"})
    assert res.status_code == 200
