def test_create_cycle_and_duplicate_prevention(client, auth_header):
    """验证打卡逻辑及重复打卡拦截（UNIQUE KEY 校验）"""
    log_data = {"start_date": "2026-08-01"}

    # 第一次打卡
    res1 = client.post("/api/v1/log_start", json=log_data, headers=auth_header)
    assert res1.status_code == 200

    # 重复打卡同一天：仍存在进行中周期，应返回 400 conflict
    res2 = client.post("/api/v1/log_start", json=log_data, headers=auth_header)
    assert res2.status_code == 400
    assert res2.json()["error"]["code"] == "conflict"
    assert "存在进行中的周期" in res2.json()["error"]["message"]


def test_daily_log_creation(client, auth_header):
    """验证精细化打卡记录写入"""
    daily_payload = {
        "log_date": "2026-08-05",
        "mood_level": 1,
        "cramps_severity": 0,
        "is_exercise": True,
        "exercise_type": "瑜伽",
        "exercise_minutes": 45,
        "diet_tag": "清淡",
        "journal_text": "今天状态不错"
    }
    res = client.post("/api/v1/daily_log", json=daily_payload, headers=auth_header)
    assert res.status_code == 200


def test_log_start_rejects_backdated_start_when_open_cycle_exists(client, auth_header):
    """当前存在进行中的周期时，不允许再插入更早的开始日期。"""
    res1 = client.post("/api/v1/log_start", json={"start_date": "2026-08-01"}, headers=auth_header)
    assert res1.status_code == 200

    res2 = client.post("/api/v1/log_start", json={"start_date": "2026-08-06"}, headers=auth_header)
    assert res2.status_code == 200

    res3 = client.post("/api/v1/log_start", json={"start_date": "2026-08-05"}, headers=auth_header)
    assert res3.status_code == 400
    assert "进行中的周期" in res3.json()["error"]["message"]


def test_log_end_rejects_overlap_when_cycle_id_is_specified(client, auth_header):
    """指定 cycle_id 修正历史周期时，也不能越过后续周期。"""
    res1 = client.post("/api/v1/log_start", json={"start_date": "2026-08-01"}, headers=auth_header)
    assert res1.status_code == 200

    res2 = client.post("/api/v1/log_end", json={"end_date": "2026-08-04"}, headers=auth_header)
    assert res2.status_code == 200

    res3 = client.post("/api/v1/log_start", json={"start_date": "2026-08-06"}, headers=auth_header)
    assert res3.status_code == 200

    stats_res = client.get("/api/v1/stats", headers=auth_header)
    assert stats_res.status_code == 200
    cycle1_id = next(
        cycle["cycle_id"]
        for cycle in stats_res.json()["cycles"]
        if cycle["start_date"] == "2026-08-01"
    )

    res4 = client.post(
        "/api/v1/log_end",
        json={"end_date": "2026-08-06", "cycle_id": cycle1_id},
        headers=auth_header,
    )
    assert res4.status_code == 400
    assert "重叠" in res4.json()["error"]["message"]


def test_daily_log_rejects_out_of_range_values(client, auth_header):
    """每日日志的枚举值应由后端强校验。"""
    payload = {
        "log_date": "2026-08-05",
        "mood_level": 9,
        "cramps_severity": 0,
        "is_exercise": True,
        "exercise_type": "瑜伽",
        "exercise_minutes": 45,
        "diet_tag": "清淡",
        "journal_text": "今天状态不错"
    }
    res = client.post("/api/v1/daily_log", json=payload, headers=auth_header)
    assert res.status_code == 422


def test_deleting_latest_cycle_clears_stale_length(client, auth_header):
    """删除后继周期后，最后一个周期不能保留旧的推导长度。"""
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-01"}, headers=auth_header
    ).status_code == 200
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-10"}, headers=auth_header
    ).status_code == 200

    cycles = client.get("/api/v1/stats", headers=auth_header).json()["cycles"]
    latest_cycle_id = next(cycle["cycle_id"] for cycle in cycles if cycle["start_date"] == "2026-08-10")
    first_cycle_id = next(cycle["cycle_id"] for cycle in cycles if cycle["start_date"] == "2026-08-01")
    assert next(cycle for cycle in cycles if cycle["cycle_id"] == first_cycle_id)["cycle_length"] == 9

    assert client.delete(f"/api/v1/cycles/{latest_cycle_id}", headers=auth_header).status_code == 200
    remaining = client.get("/api/v1/stats", headers=auth_header).json()["cycles"]
    assert remaining[0]["cycle_length"] is None


def test_cycle_update_null_end_date_reopens_cycle(client, auth_header):
    """显式传 end_date=null 应取消周期闭合。"""
    assert client.post(
        "/api/v1/log_start", json={"start_date": "2026-08-01"}, headers=auth_header
    ).status_code == 200
    assert client.post(
        "/api/v1/log_end", json={"end_date": "2026-08-03"}, headers=auth_header
    ).status_code == 200
    cycles = client.get("/api/v1/stats", headers=auth_header).json()["cycles"]
    cycle_id = cycles[0]["cycle_id"]

    response = client.put(
        f"/api/v1/cycles/{cycle_id}", json={"end_date": None}, headers=auth_header
    )
    assert response.status_code == 200
    cycle = client.get("/api/v1/stats", headers=auth_header).json()["cycles"][0]
    assert cycle["end_date"] is None
    assert cycle["cycle_length"] is None
