"""Inspect the released model without reading the user database."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.core.config import settings
from app.ml.contract import FEATURE_NAMES, MODEL_VERSION
from app.services.cycle_prediction_service import CyclePredictionService


def main() -> None:
    model_path = Path(settings.model_abs_path)
    if not model_path.exists():
        raise SystemExit(f"模型不存在: {model_path}")

    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if settings.MODEL_SHA256 and digest != settings.MODEL_SHA256:
        raise SystemExit("模型 SHA-256 与配置不一致")

    model = CyclePredictionService().model
    if model is None or not hasattr(model, "feature_importances_"):
        raise SystemExit("安全模型未加载或不支持特征重要性")

    importance = pd.DataFrame(
        {"feature": FEATURE_NAMES, "importance": model.feature_importances_}
    ).sort_values("importance", ascending=False)
    importance["importance_percent"] = (importance["importance"] * 100).round(2)

    print(f"model_version={MODEL_VERSION}")
    print(f"sha256={digest}")
    print(f"features={getattr(model, 'n_features_in_', None)}")
    print(importance[["feature", "importance_percent"]].to_string(index=False))


if __name__ == "__main__":
    main()
