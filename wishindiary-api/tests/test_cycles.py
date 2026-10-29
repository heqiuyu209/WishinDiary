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


def test_next_start_updates_length_after_recorded_end(client, auth_header):
    for path, payload in [
        ("log_start", {"start_date": "2024-01-01"}),
        ("log_end", {"end_date": "2024-01-05"}),
        ("log_start", {"start_date": "2024-01-29"}),
    ]:
        assert client.post(f"/api/v1/{path}", json=payload).status_code == 200
    cycles = client.get("/api/v1/stats").json()["cycles"]
    assert cycles[0]["cycle_length"] == 28
    assert cycles[0]["end_date"] == "2024-01-05"
    assert client.get("/api/v1/prediction").json()["status"] == "success"


def test_missing_previous_end_does_not_fabricate_dates_or_block_latest_end(client, auth_header):
    for start in ["2024-01-01", "2024-01-29"]:
        assert client.post("/api/v1/log_start", json={"start_date": start}).status_code == 200
    first, latest = client.get("/api/v1/stats").json()["cycles"]
    assert first["cycle_length"] == 28
    assert first["end_date"] is None
    assert first["bleeding_days"] is None
    assert client.post("/api/v1/log_end", json={"end_date": "2024-02-02"}).status_code == 200
    # 默认修正最新记录，不能回退到历史漏记。
    assert client.post("/api/v1/log_end", json={"end_date": "2024-02-03"}).status_code == 200
    first, latest = client.get("/api/v1/stats").json()["cycles"]
    assert first["end_date"] is None
    assert latest["end_date"] == "2024-02-03"


def test_historical_unknown_end_can_be_updated_and_filled(client, auth_header):
    for start in ["2024-01-01", "2024-01-29", "2024-02-26"]:
        assert client.post("/api/v1/log_start", json={"start_date": start}).status_code == 200
    first, middle, _ = client.get("/api/v1/stats").json()["cycles"]
    response = client.put(
        f"/api/v1/cycles/{middle['cycle_id']}",
        json={"start_date": "2024-01-30", "end_date": None},
    )
    assert response.status_code == 200, response.text
    assert client.post("/api/v1/log_end", json={
        "cycle_id": first["cycle_id"], "end_date": "2024-01-05",
    }).status_code == 200
    rows = client.get("/api/v1/stats").json()["cycles"]
    assert rows[0]["cycle_length"] == 29
    assert rows[1]["cycle_length"] == 27
    assert rows[1]["end_date"] is None
    assert client.post("/api/v1/log_end", json={
        "cycle_id": rows[1]["cycle_id"], "end_date": "2024-02-26",
    }).status_code == 400
