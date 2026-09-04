def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200

def test_prediction_insufficient_data(client):
    # 测试未鉴权或无数据情况下的契约返回
    response = client.get("/api/v1/prediction")
    assert response.status_code == 401


def test_prediction_contract_fields(client, auth_header):
    """预测成功时，响应必须携带 model_version、置信区间与免责声明。"""
    from datetime import date, timedelta

    # 需要至少 4 个完整周期才能形成有效特征窗口
    start_dates = ["2026-01-01", "2026-01-29", "2026-02-27", "2026-03-27", "2026-04-25"]
    for sd in start_dates:
        assert client.post("/api/v1/log_start", json={"start_date": sd}, headers=auth_header).status_code == 200
        start_obj = date.fromisoformat(sd)
        end_obj = start_obj + timedelta(days=5)
        assert client.post(
            "/api/v1/log_end", json={"end_date": end_obj.isoformat()}, headers=auth_header
        ).status_code == 200

    res = client.get("/api/v1/prediction", headers=auth_header)
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "success"
    prediction = payload["prediction"]
    assert prediction["model_version"]  # 非空模型版本
    assert "confidence_interval" in prediction  # 置信区间字段存在
    if prediction["confidence_interval"] is not None:
        assert prediction["confidence_interval"]["low"] <= prediction["confidence_interval"]["high"]
    assert "不能用于诊断" in prediction["disclaimer"]  # 免责声明


def test_stats_returns_empty_payload(client, auth_header):
    response = client.get("/api/v1/stats", headers=auth_header)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["cycles"] == []
    assert payload["recent_logs"] == []


def test_report_returns_default_summary(client, auth_header):
    response = client.get("/api/v1/report", headers=auth_header)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["report"]["total_recorded_cycles"] == 0


def test_session_returns_authenticated_user(client, auth_header):
    # The browser path authenticates through the HttpOnly cookie, not storage.
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["username"] == "test_user"
