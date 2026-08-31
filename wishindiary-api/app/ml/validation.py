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
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    ordered = feature_matrix.sort_values("start_date").reset_index(drop=True)
    cut = max(1, int(len(ordered) * (1 - test_fraction)))
    return ordered.index[:cut].to_numpy(), ordered.index[cut:].to_numpy()


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
