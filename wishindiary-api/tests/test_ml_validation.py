"""Temporal evaluation must preserve positions and label availability."""
import pandas as pd
import pytest

from app.ml.validation import build_temporal_holdout_split
from scripts.train import _collect_env_metadata


def test_unsorted_dates_return_original_positions_not_sorted_frame_indices():
    frame = pd.DataFrame({"start_date": pd.to_datetime([
        "2025-01-01", "2020-01-01", "2024-01-01", "2021-01-01"
    ])}, index=[10, 50, 20, 90])
    train, test = build_temporal_holdout_split(frame, 0.5)
    assert set(train) == {1, 3}
    assert set(test) == {0, 2}
    assert frame.iloc[train].start_date.max() < frame.iloc[test].start_date.min()


def test_equal_dates_are_not_split_across_train_and_test():
    frame = pd.DataFrame({"start_date": pd.to_datetime([
        "2026-01-01", "2026-02-01", "2026-02-01", "2026-03-01"
    ])})
    train, test = build_temporal_holdout_split(frame, 0.5)
    assert train.tolist() == [0]
    assert test.tolist() == [1, 2, 3]


def test_unfinished_training_labels_are_excluded_at_prediction_boundary():
    frame = pd.DataFrame({
        "start_date": pd.to_datetime(["2026-01-01", "2026-01-20", "2026-02-01", "2026-03-01"]),
        "target_length": [28, 30, 28, 28],
    })
    train, test = build_temporal_holdout_split(frame, 0.5)
    assert train.tolist() == [0]
    assert test.tolist() == [2, 3]


@pytest.mark.parametrize("dates", [[], ["2026-01-01"], ["2026-01-01", "2026-01-01"], ["invalid", "2026-02-01"]])
def test_unusable_temporal_splits_are_explicit(dates):
    with pytest.raises(ValueError):
        build_temporal_holdout_split(pd.DataFrame({"start_date": dates}))


def test_environment_metadata_records_installed_dependency_versions():
    dependencies = _collect_env_metadata()["dependencies"]
    assert dependencies["skops"] != "not-installed"
    assert dependencies["pymysql"] != "not-installed"
    assert dependencies["python"]
