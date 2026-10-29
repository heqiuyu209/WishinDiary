"""Regression tests for the forecast's history/target time boundary."""
from datetime import date, timedelta
import math
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.features import cycle_feature_engineering as feature_module
from app.features.cycle_feature_engineering import build_cycle_feature_matrix, build_prediction_feature_row
from app.ml.contract import FEATURE_NAMES


def _history(lengths=(24, 25, 26, 42)):
    start = date(2026, 1, 1)
    rows = []
    for idx, length in enumerate(lengths):
        rows.append({"user_id": 1, "start_date": start,
                     "cycle_length": length, "bleeding_days": idx + 4})
        start += timedelta(days=length)
    return pd.DataFrame(rows), start


def test_next_cycle_uses_newest_completed_length_and_current_month():
    history, anchor = _history()
    features = build_prediction_feature_row(history, anchor)
    assert [features[f"lag_{idx}_length"] for idx in (1, 2, 3)] == [42, 26, 25]
    assert [features[f"lag_{idx}_bleeding"] for idx in (1, 2, 3)] == [7, 6, 5]
    assert features["roll_3_mean"] == 31
    assert features["roll_3_std"] == pytest.approx(pd.Series([25, 26, 42]).std())
    assert features["start_month_sin"] == pytest.approx(math.sin(2 * math.pi * 3 / 12))
    assert set(features) == set(FEATURE_NAMES)


def test_inference_matches_training_row_when_target_is_appended():
    history, anchor = _history()
    history.loc[3, "bleeding_days"] = None
    row = {"user_id": 1, "start_date": anchor, "cycle_length": 30, "bleeding_days": 6}
    X, _, _ = build_cycle_feature_matrix(pd.concat([history, pd.DataFrame([row])]), pd.DataFrame())
    assert build_prediction_feature_row(history, anchor) == pytest.approx(X.iloc[-1].to_dict())


def test_api_feature_extraction_retains_all_history_for_personalization(monkeypatch):
    history, anchor = _history((23, 24, 25, 26, 42))
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = {"start_date": anchor}
    monkeypatch.setattr(feature_module, "_connect_db", lambda: connection)
    monkeypatch.setattr(feature_module, "_read_sql_dataframe", lambda *args, **kwargs: history)
    features, actual_anchor, count, mean = feature_module.get_latest_features_for_user(1)
    assert features["lag_1_length"] == 42
    assert actual_anchor == anchor
    assert count == 5
    assert mean == 28
    connection.close.assert_called_once()


def test_history_order_does_not_change_inference():
    history, anchor = _history()
    assert build_prediction_feature_row(history.iloc[::-1], anchor) == build_prediction_feature_row(history, anchor)
