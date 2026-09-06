"""B 任务：注册时可选补录最近经期开始日期 + 预测数据门槛降级测试。

覆盖目标：
- 注册补录 2~4 个经期开始日期 → cycles 正确写入且 recalculate 周期长度；
- 校验拒绝：未来日期 / 重复日期 / 仅 1 个日期 / 相邻间隔超 15~60 天 / 超过 4 个；
- 补录 >=2 个日期组成至少 1 个完整周期后，预测立即可用（基础统计量模式），
  否则维持原 insufficient_data 语义（绕过"至少 4 个完整周期"门槛）。
"""

from datetime import date, timedelta

import pytest


def _dates_offsets(*offsets: int) -> list[str]:
    """按相对今天的偏移构造日期字符串，返回按时间升序（更早在前）。

    偏移为负表示过去（如 -56 = 56 天前），正表示未来。
    """
    today = date.today()
    return [(today + timedelta(days=o)).isoformat() for o in sorted(offsets)]


def _register(client, username: str, period_dates: list[str] | None) -> object:
    payload = {"username": username, "password": "password123"}
    if period_dates is not None:
        payload["period_start_dates"] = period_dates
    return client.post("/api/v1/auth/register", json=payload)


def _login(client, username: str = "bf_user") -> None:
    assert client.post(
        "/api/v1/auth/login", json={"username": username, "password": "password123"}
    ).status_code == 200


class TestRegisterBackfillWrites:
    def test_two_dates_write_one_complete_cycle(self, client):
        d_prev, d_latest = _dates_offsets(-56, -28)  # 相邻间隔 28 天
        resp = _register(client, "bf_user", [d_prev, d_latest])
        assert resp.status_code == 200
        body = resp.json()
        assert body["period_dates_recorded"] == 2

        _login(client)
        stats = client.get("/api/v1/stats").json()
        cycles = stats["cycles"]
        assert len(cycles) == 2
        by_start = {c["start_date"]: c for c in cycles}
        assert by_start[d_prev]["cycle_length"] == 28
        # 最新周期无后继，长度置 NULL
        assert by_start[d_latest]["cycle_length"] is None

    def test_four_dates_write_three_complete_cycles(self, client):
        dates = _dates_offsets(-112, -84, -56, -28)
        resp = _register(client, "bf_user", dates)
        assert resp.status_code == 200
        assert resp.json()["period_dates_recorded"] == 4

        _login(client)
        cycles = client.get("/api/v1/stats").json()["cycles"]
        assert len(cycles) == 4
        by_start = {c["start_date"]: c for c in cycles}
        for d in dates[:-1]:
            assert by_start[d]["cycle_length"] == 28
        assert by_start[dates[-1]]["cycle_length"] is None

    def test_register_without_backfill_writes_nothing(self, client):
        resp = _register(client, "bf_user", None)
        assert resp.status_code == 200
        assert resp.json()["period_dates_recorded"] == 0

        _login(client)
        assert client.get("/api/v1/stats").json()["cycles"] == []


class TestRegisterBackfillValidation:
    @pytest.mark.parametrize(
        ("offsets", "label"),
        [
            ((1,), "未来日期"),
            ((-28, -28), "重复日期"),
            ((-28,), "仅 1 个日期不足一个完整周期"),
            ((-48, -38), "相邻间隔 10 天过短"),
            ((-90, -20), "相邻间隔 70 天过长"),
        ],
    )
    def test_rejects_invalid_backfill(self, client, offsets, label):
        dates = _dates_offsets(*offsets)
        resp = _register(client, "bf_user", dates)
        assert resp.status_code == 422, f"{label} 应被拒绝: {resp.text}"
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["message"] == "请求参数校验失败"

    def test_rejects_more_than_four_dates(self, client):
        dates = _dates_offsets(-140, -112, -84, -56, -28)
        resp = _register(client, "bf_user", dates)
        # Pydantic max_length 触发 422
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"


class TestPredictionBackfillUnlock:
    def test_backfilled_two_dates_unlock_basic_prediction(self, client):
        d_prev, d_latest = _dates_offsets(-56, -28)
        assert _register(client, "bf_user", [d_prev, d_latest]).status_code == 200

        _login(client)
        res = client.get("/api/v1/prediction")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "success"
        pred = body["prediction"]
        assert pred["last_period_start"] == d_latest
        assert 21 <= pred["predicted_cycle_length"] <= 45
        assert "基础统计量模式" in pred["features_info"]
        assert pred["confidence_interval"]["low"] <= pred["confidence_interval"]["high"]
        assert "不能用于诊断" in pred["disclaimer"]

    def test_backfilled_four_dates_still_uses_basic_stats(self, client):
        # 4 个经期开始日 → 3 条完整周期 < 4，仍走基础统计量模式
        dates = _dates_offsets(-112, -84, -56, -28)
        assert _register(client, "bf_user", dates).status_code == 200

        _login(client)
        body = client.get("/api/v1/prediction").json()
        assert body["status"] == "success"
        pred = body["prediction"]
        assert pred["last_period_start"] == dates[-1]
        assert "基础统计量模式" in pred["features_info"]

    def test_without_backfill_stays_insufficient(self, client):
        assert _register(client, "bf_user", None).status_code == 200
        _login(client)
        body = client.get("/api/v1/prediction").json()
        assert body["status"] == "insufficient_data"
        assert body["prediction"] is None
