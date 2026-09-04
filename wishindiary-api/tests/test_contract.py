"""API 契约测试。

覆盖目标：
- OpenAPI schema 暴露全部 /api/v1 版本化路由；
- 统一错误响应格式 {"error": {"code", "message", "detail"}} 对 401/400/409/422 均生效；
- 关键业务接口的响应体结构保持稳定（避免前端契约静默破坏）。
"""


# 期望在 OpenAPI 中暴露的路径（版本化契约基线）
EXPECTED_PATHS = {
    "/api/health",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/session",
    "/api/v1/log_start",
    "/api/v1/log_end",
    "/api/v1/cycles/{cycle_id}",
    "/api/v1/daily_log",
    "/api/v1/prediction",
    "/api/v1/stats",
    "/api/v1/report",
    "/api/v1/user/me",
    "/api/v1/user/export",
}


def _assert_unified_error(body):
    assert set(body.keys()) == {"error"}, f"错误响应应仅含 error 字段，实际: {body}"
    assert set(body["error"].keys()) == {"code", "message", "detail"}, (
        f"error 对象应含 code/message/detail，实际: {body['error']}"
    )


def test_openapi_exposes_versioned_api_paths(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    actual = set(spec.json()["paths"].keys())
    missing = EXPECTED_PATHS - actual
    assert not missing, f"OpenAPI 缺失契约路径: {sorted(missing)}"


def test_health_endpoint_contract(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert set(body.keys()) == {"status", "database", "message"}


def test_unauthorized_returns_unified_error(client):
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 401
    _assert_unified_error(resp.json())
    assert resp.json()["error"]["code"] == "unauthorized"


def test_user_me_contract(client):
    """/api/v1/user/me 仅暴露 DELETE（数据被遗忘权），契约不得被其它方法破坏。"""
    spec = client.get("/openapi.json").json()
    methods = set(spec["paths"]["/api/v1/user/me"].keys())
    assert methods == {"delete"}, f"/api/v1/user/me 应仅支持 delete，实际: {methods}"


def test_registration_conflict_returns_unified_error(client):
    payload = {"username": "contract_dup", "password": "password123"}
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 200

    dup = client.post("/api/v1/auth/register", json=payload)
    assert dup.status_code == 400
    _assert_unified_error(dup.json())
    assert dup.json()["error"]["code"] == "invalid_input"
    assert dup.json()["error"]["message"] == "用户名已存在"


def test_validation_error_returns_unified_shape(auth_header, client):
    # 已登录前提下发送非法 start_date → 422，应收敛为统一错误结构
    resp = client.post("/api/v1/log_start", json={"start_date": "not-a-date"})
    assert resp.status_code == 422
    _assert_unified_error(resp.json())
    assert resp.json()["error"]["code"] == "validation_error"


def test_cycle_response_contract(auth_header, client):
    resp = client.post(
        "/api/v1/log_start",
        json={"start_date": "2026-09-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"status", "message"}
    assert body["status"] == "success"


def test_daily_log_response_contract(auth_header, client):
    resp = client.post(
        "/api/v1/daily_log",
        json={
            "log_date": "2026-09-01",
            "mood_level": 1,
            "cramps_severity": 1,
            "is_exercise": False,
            "is_intercourse": False,
            "exercise_type": None,
            "exercise_minutes": 0,
            "diet_tag": None,
            "journal_text": "一切正常",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "ai_health_advice" in body
    assert isinstance(body["ai_health_advice"], list)
