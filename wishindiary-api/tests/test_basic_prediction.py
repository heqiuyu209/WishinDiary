from datetime import date

import pandas as pd

from app.features.cycle_feature_engineering import prepare_ml_history
from app.ml.basic_prediction import build_basic_prediction


def test_basic_prediction_preserves_cold_start_rounding_guardrail_and_interval():
    history = [{"cycle_length": 27}, {"cycle_length": 28}]
    result = build_basic_prediction(history, date(2024, 1, 1))
    assert result["predicted_cycle_length"] == 28
    assert result["next_period_start"] == "2024-01-29"
    assert result["confidence_interval"]["low"] == 27.5
    assert result["confidence_interval"]["high"] == 28.5
    long = build_basic_prediction([{"cycle_length": 60}], date(2024, 1, 1))
    assert long["raw_predicted_cycle_length"] == 60
    assert long["predicted_cycle_length"] == 45


def test_basic_prediction_requires_known_history_and_anchor():
    assert build_basic_prediction([], date(2024, 1, 1)) is None
    assert build_basic_prediction([{"cycle_length": None}], date(2024, 1, 1)) is None
    assert build_basic_prediction([{"cycle_length": 28}], None) is None


def test_ml_history_limits_before_filtering_and_keeps_missing_bleeding():
    history = pd.DataFrame({
        "start_date": pd.date_range("2020-01-01", periods=55, freq="30D"),
        "cycle_length": [28] * 53 + [80, 28],
        "bleeding_days": [None] * 54 + [30],
    })
    clean = prepare_ml_history(history.iloc[::-1])
    assert len(clean) == 48
    assert clean.start_date.min() == history.start_date.iloc[5]
    assert clean.bleeding_days.isna().all()
