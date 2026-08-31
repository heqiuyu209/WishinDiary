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
