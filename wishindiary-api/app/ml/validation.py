"""Small, dependency-light validation helpers for offline model evaluation."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.model_selection import GroupKFold


def build_group_kfold_splits(X: pd.DataFrame, groups: pd.Series, n_splits: int = 5) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    unique_groups = int(groups.nunique())
    if unique_groups < 2:
        raise ValueError("GroupKFold requires at least two distinct users")
    n_splits = max(2, min(n_splits, unique_groups))
    return GroupKFold(n_splits=n_splits).split(X, groups=groups)


def build_temporal_holdout_split(feature_matrix: pd.DataFrame, test_fraction: float = 0.2):
    """Return original row positions, keeping equal-date observations together.

    A training target is only available when that cycle has finished. Exclude
    targets spanning the held-out prediction boundary when lengths are known.
    """
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    if len(feature_matrix) < 2:
        raise ValueError("Temporal validation requires at least two samples")
    dates = pd.to_datetime(feature_matrix["start_date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("Temporal validation requires valid start dates")
    order = np.argsort(dates.to_numpy(), kind="stable")
    cut = min(len(order) - 1, max(1, int(len(order) * (1 - test_fraction))))
    boundary = dates.iloc[order[cut]]
    train_idx = np.flatnonzero((dates < boundary).to_numpy())
    test_idx = np.flatnonzero((dates >= boundary).to_numpy())
    if "target_length" in feature_matrix:
        available_at = dates + pd.to_timedelta(feature_matrix["target_length"], unit="D")
        train_idx = train_idx[(available_at.iloc[train_idx] <= boundary).to_numpy()]
    if not len(train_idx) or not len(test_idx):
        raise ValueError("Temporal boundary leaves no usable training or test samples")
    return train_idx, test_idx


def evaluate_regression_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
    }


def summarize_feature_matrix(X: pd.DataFrame) -> dict[str, object]:
    return {
        "rows": int(len(X)),
        "columns": list(X.columns),
        "missing_values": int(X.isna().sum().sum()),
    }
