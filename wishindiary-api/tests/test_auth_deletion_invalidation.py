"""B2 安全测试：账号删除后，旧 access token 立即失效，不能继续访问业务数据。"""


def test_old_access_token_rejected_after_account_deletion(client):
    """删除账号前会话有效；删除后同一 access token 访问 /session 应 401。"""
    payload = {"username": "deleted_user", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 200
    assert client.post("/api/v1/auth/login", json=payload).status_code == 200

    # 登录态有效
    assert client.get("/api/v1/auth/session").status_code == 200

    # 删除账号（级联清理全部健康数据）
    res = client.delete("/api/v1/user/me")
    assert res.status_code == 200, res.text

    # 旧 access token（仍携带于 Cookie）必须立即失效
    resp = client.get("/api/v1/auth/session")
    assert resp.status_code == 401
    assert "账号不存在" in resp.json()["error"]["message"]


def test_deleted_user_protected_route_rejected(client):
    """删除账号后，受保护的业务数据接口也应被 401 拦截。"""
    payload = {"username": "deleted_data_user", "password": "password123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 200
    assert client.post("/api/v1/auth/login", json=payload).status_code == 200
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-01"}
    ).status_code == 200

    assert client.delete("/api/v1/user/me").status_code == 200
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 401
