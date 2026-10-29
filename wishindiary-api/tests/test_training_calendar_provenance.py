"""Synthetic CSV fixtures must not turn invented dates into seasonal evidence."""

import json

import pandas as pd
import pytest
import skops.io as sio

from app.features import build_cycle_feature_matrix
from app.ml.contract import FEATURE_NAMES
from app.ml.validation import build_temporal_holdout_split
from scripts import train


@pytest.fixture
def cycle_order_csv(tmp_path):
    path = tmp_path / "synthetic_cycle_order.csv"
    pd.DataFrame([
        {"ClientID": f"synthetic{user}", "CycleNumber": cycle + 1,
         "LengthofCycle": 26 + (cycle + user) % 8, "LengthofMenses": 4 + cycle % 2}
        for user in range(6) for cycle in range(10)
    ]).to_csv(path, index=False)
    return path


def test_csv_order_dates_disable_months_and_calendar_holdout(cycle_order_csv):
    cycles, logs = train.load_fedcycle_csv(str(cycle_order_csv))
    assert cycles.attrs["calendar_provenance"] == "synthetic_cycle_order"
    X, _, metadata = build_cycle_feature_matrix(cycles, logs)
    assert tuple(X.columns) == FEATURE_NAMES
    assert X[["start_month_sin", "start_month_cos"]].eq(0.0).all().all()
    assert metadata["calendar_provenance"].eq("synthetic_cycle_order").all()
    with pytest.raises(ValueError, match="placeholders"):
        build_temporal_holdout_split(metadata)


def test_csv_training_report_and_model_preserve_disabled_calendar_policy(
    cycle_order_csv, tmp_path, monkeypatch,
):
    model_file = tmp_path / "fixture_model.skops"
    monkeypatch.setattr(train.settings, "MODEL_PATH", str(model_file))
    # The CSV path must not invoke real-calendar validation or synthetic fallback.
    monkeypatch.setattr(train, "build_temporal_holdout_split", lambda *a, **k: pytest.fail("calendar holdout called"))
    monkeypatch.setattr(train, "build_synthetic_training_data", lambda: pytest.fail("synthetic fallback called"))
    train.train_and_evaluate(csv_path=str(cycle_order_csv))
    report = json.loads((tmp_path / "model_evaluation_report.json").read_text())
    assert report["dataset"]["calendar_provenance"] == ["synthetic_cycle_order"]
    assert report["dataset"]["calendar_features_enabled"] is False
    assert report["temporal_holdout"]["status"] == "not_applicable"
    assert report["metadata"]["feature_contract"]["disabled_features"] == [
        "start_month_sin", "start_month_cos",
    ]
    assert report["group_kfold"]["n_splits"] == 5
    model = sio.load(model_file)
    assert tuple(model.feature_names_in_) == FEATURE_NAMES
    assert list(model.feature_importances_[-2:]) == [0.0, 0.0]


def test_recorded_calendar_still_uses_actual_months():
    cycles = pd.DataFrame({
        "user_id": [1] * 5, "start_date": pd.date_range("2024-01-01", periods=5, freq="28D"),
        "cycle_length": [28] * 5, "bleeding_days": [5] * 5,
    })
    X, _, metadata = build_cycle_feature_matrix(cycles, pd.DataFrame())
    assert X[["start_month_sin", "start_month_cos"]].ne(0).any().any()
    assert metadata["calendar_provenance"].eq("recorded_calendar").all()


def test_calendar_validation_rejects_placeholder_provenance_in_attrs():
    frame = pd.DataFrame({"start_date": ["2024-01-01", "2024-02-01"]})
    frame.attrs["calendar_provenance"] = "synthetic_cycle_order"
    with pytest.raises(ValueError, match="placeholders"):
        build_temporal_holdout_split(frame)
