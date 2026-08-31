def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200

def test_prediction_insufficient_data(client):
    # 测试未鉴权或无数据情况下的契约返回
    response = client.get("/api/prediction")
    assert response.status_code == 401


def test_stats_returns_empty_payload(client, auth_header):
    response = client.get("/api/stats", headers=auth_header)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["cycles"] == []
    assert payload["recent_logs"] == []


def test_report_returns_default_summary(client, auth_header):
    response = client.get("/api/report", headers=auth_header)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["report"]["total_recorded_cycles"] == 0


def test_session_returns_authenticated_user(client, auth_header):
    # The browser path authenticates through the HttpOnly cookie, not storage.
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    assert response.json()["username"] == "test_user"
