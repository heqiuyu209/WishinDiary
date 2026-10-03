"""数据质量提示（疑似漏记/过短周期）单元测试。

覆盖纯函数及真实 API 链路，确保模型过滤不会吞掉异常记录。
"""
from datetime import date, timedelta

import pytest

from app.services.prediction_service import build_data_quality_warnings


def _features(lag1, lag2, lag3):
    return {
        "lag_1_length": None if lag1 is None else float(lag1),
        "lag_2_length": None if lag2 is None else float(lag2),
        "lag_3_length": None if lag3 is None else float(lag3),
        "lag_1_bleeding": 5.0,
        "lag_2_bleeding": 5.0,
        "lag_3_bleeding": 5.0,
        "roll_3_mean": 28.0,
        "roll_3_std": 2.0,
        "start_month_sin": 0.0,
        "start_month_cos": 1.0,
    }


def test_normal_cycles_no_warning():
    assert build_data_quality_warnings(_features(28, 27, 29)) == []


def test_missing_period_detected():
    """27/29/58：58 天远超常规，提示疑似漏记一次开始。"""
    warnings = build_data_quality_warnings(_features(58, 27, 29))
    assert len(warnings) == 1
    assert "漏" in warnings[0]
    assert "58" in warnings[0]


def test_missing_period_should_not_trigger_with_no_break():
    """32/33/30 虽略长但在合理范围，不产生提示。"""
    assert build_data_quality_warnings(_features(32, 33, 30)) == []


def test_suspicious_short_cycle_detected():
    """16/28/29：16 天明显过短，提示可能重复标记。"""
    warnings = build_data_quality_warnings(_features(16, 28, 29))
    assert len(warnings) == 1
    assert "短" in warnings[0]


def test_insufficient_plausible_samples_returns_empty():
    """有效样本不足 2 条时不提示（避免弱数据误报）。"""
    assert build_data_quality_warnings(_features(None, None, 28)) == []


def test_dirty_long_interval_still_reported():
    """65 天不参与基线计算（plausible 仅 28/30，baseline=29），但仍应作为异常间隔提示漏记。"""
    warnings = build_data_quality_warnings(_features(65, 28, 30))
    assert len(warnings) == 1
    assert "漏" in warnings[0]


@pytest.mark.parametrize("intervals, wording", [
    ([28, 28, 28, 28, 56], "漏"),  # ML 路径：56 天不进入模型窗口。
    ([28, 28, 12], "短"),  # 基础统计路径也要检查原始间隔。
])
def test_prediction_checks_raw_intervals_before_filtering(client, auth_header, intervals, wording):
    current = date(2024, 1, 1)
    for length in [*intervals, None]:
        response = client.post("/api/v1/log_start", json={"start_date": current.isoformat()})
        assert response.status_code == 200, response.text
        if length:
            current += timedelta(days=length)
    response = client.get("/api/v1/prediction")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "outside_model_scope"
    warnings = response.json()["data_quality_warnings"]
    assert warnings and any(wording in warning for warning in warnings)
    assert str(intervals[-1]) in warnings[0]


def test_normal_raw_history_has_no_warning(client, auth_header):
    for start in ["2024-01-01", "2024-01-29", "2024-02-26"]:
        assert client.post("/api/v1/log_start", json={"start_date": start}).status_code == 200
    assert client.get("/api/v1/prediction").json()["prediction"]["data_quality_warnings"] is None


def test_repeated_long_cycles_abstain_without_snapshot(client, auth_header):
    current = date(2024, 1, 1)
    for _ in range(4):
        assert client.post("/api/v1/log_start", json={"start_date": current.isoformat()}).status_code == 200
        current += timedelta(days=60)
    body = client.get("/api/v1/prediction").json()
    assert body["status"] == "outside_model_scope"
    assert body["prediction"] is None
    assert any("60" in item for item in body["data_quality_warnings"])
    from app.core.database import transaction
    with transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM prediction_logs")
            assert cursor.fetchone()["n"] == 0
