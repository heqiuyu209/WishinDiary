"""数据质量提示（疑似漏记/过短周期）单元测试。

只测纯函数 build_data_quality_warnings，不依赖数据库。
"""
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
