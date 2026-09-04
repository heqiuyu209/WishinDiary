from datetime import date, timedelta

import pandas as pd

from app.features.cycle_feature_engineering import build_cycle_feature_matrix


def test_rolling_features_are_isolated_per_user():
    rows = []
    for user_id in (1, 2):
        start = date(2026, 1, 1)
        for length in (28, 29, 30, 31):
            rows.append({
                "user_id": user_id,
                "start_date": start,
                "cycle_length": length,
                "bleeding_days": None,
            })
            start += timedelta(days=length)

    X, y, matrix = build_cycle_feature_matrix(pd.DataFrame(rows), pd.DataFrame())

    assert len(X) == 2
    assert len(y) == 2
    assert set(matrix["user_id"]) == {1, 2}
    assert set(matrix["roll_3_mean"]) == {29.0}


def test_start_month_sin_cos_circular_encoding():
    """P0-1：start_month 循环编码。1 月与 12 月在单位圆上应相邻（不再是整数断崖）。"""
    rows = []
    for month in (1, 2, 3, 12):
        rows.append({
            "user_id": 1,
            "start_date": date(2026, month, 1),
            "cycle_length": 28,
            "bleeding_days": None,
        })

    X, _, _ = build_cycle_feature_matrix(pd.DataFrame(rows), pd.DataFrame())
    assert list(X.columns) == [
        "lag_1_length", "lag_2_length", "lag_3_length",
        "lag_1_bleeding", "lag_2_bleeding", "lag_3_bleeding",
        "roll_3_mean", "roll_3_std",
        "start_month_sin", "start_month_cos",
    ]

    # 窗口内最近一期 start_date 是 2026-12-01（12 月）：
    #   sin(2π*(12-1)/12) = sin(11π/6) ≈ -0.5
    #   cos(2π*(12-1)/12) = cos(11π/6) ≈ +0.866（与 1 月 cos(0)=1 相邻，体现循环性）
    import math

    last = X.iloc[-1]
    rad = 2.0 * math.pi * (12 - 1) / 12.0
    assert abs(last["start_month_cos"] - math.cos(rad)) < 1e-9
    assert abs(last["start_month_sin"] - math.sin(rad)) < 1e-9
    assert abs(last["start_month_cos"] - 0.8660254037844387) < 1e-6  # cos(11π/6)
    assert abs(last["start_month_sin"] - (-0.5)) < 1e-6             # sin(11π/6)
    assert -1.0 <= last["start_month_sin"] <= 1.0
    assert -1.0 <= last["start_month_cos"] <= 1.0
