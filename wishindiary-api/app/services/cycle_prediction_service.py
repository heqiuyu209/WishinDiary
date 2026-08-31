"""Cycle prediction inference service.

使用离线预训练的随机森林模型进行推理（不在请求时训练）。
模型由 `scripts/train.py` 离线训练并保存为 skops，特征口径与训练一致：
    9 个滑动窗口特征 (lag_1~3_length, lag_1~3_bleeding, roll_3_mean, roll_3_std, start_month)
"""

import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import settings
from app.ml.contract import FEATURE_NAMES, MODEL_VERSION

logger = logging.getLogger(__name__)

ALLOWED_MODEL_PREFIXES = ("numpy.", "sklearn.", "scipy.")


class CyclePredictionService:
    """加载离线模型，用用户最新窗口特征推理，并计算医学日期。"""

    def __init__(self):
        self.model = self._load_model()

    def _load_model(self):
        """Load a signed skops model; never execute arbitrary pickle payloads."""
        model_path = Path(settings.model_abs_path)
        if not model_path.exists():
            logger.warning("经期预测模型不存在（仅接受安全 .skops 格式），启用无模型基线预测: %s", model_path)
            return None
        if model_path.suffix != ".skops":
            logger.error("拒绝加载非 skops 模型文件: %s", model_path)
            return None
        try:
            expected_hash = getattr(settings, "MODEL_SHA256", "")
            if expected_hash:
                actual_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise RuntimeError("模型 SHA-256 校验失败")

            import skops.io as sio

            unknown_types = set(sio.get_untrusted_types(file=model_path))
            unsafe = {name for name in unknown_types if not name.startswith(ALLOWED_MODEL_PREFIXES)}
            if unsafe:
                raise RuntimeError(f"模型包含未允许类型: {sorted(unsafe)}")
            model = sio.load(model_path, trusted=sorted(unknown_types))
            if getattr(model, "n_features_in_", len(FEATURE_NAMES)) != len(FEATURE_NAMES):
                raise RuntimeError("模型特征维度与线上契约不一致")
            trained_names = getattr(model, "feature_names_in_", None)
            if trained_names is not None and list(trained_names) != list(FEATURE_NAMES):
                raise RuntimeError("模型特征顺序与线上契约不一致")
            logger.info("经期预测模型加载成功（安全 .skops）: %s (%s)", model_path, MODEL_VERSION)
            return model
        except Exception:
            logger.exception("经期预测模型加载失败，启用无模型基线预测")
            return None

    def predict(self, features_dict: dict, last_start_date) -> dict | None:
        """用 9 特征 + 上次经期开始日期推理下一次经期。

        features_dict: 与 FEATURE_NAMES 完全对应的 9 个特征值
        last_start_date: 用户最近一次经期开始日期 (date)
        """
        try:
            row = [float(features_dict[name]) for name in FEATURE_NAMES]
            if self.model is None and settings.ENVIRONMENT == "production":
                logger.error("生产环境模型未加载，拒绝提供基线预测")
                return None
            if self.model is None:
                raw_pred_length = round(float(features_dict["roll_3_mean"]))
            else:
                raw_pred_length = round(float(self.model.predict([row])[0]))
        except (KeyError, TypeError, ValueError):
            logger.exception("推理输入无效")
            return None

        # 医学边界保护
        pred_length = max(21, min(raw_pred_length, 45))
        if pred_length != raw_pred_length:
            medical_note = (
                f"模型原始输出 {raw_pred_length} 天，已按医学边界修正为 {pred_length} 天（21-45 天）"
            )
        else:
            medical_note = "预测结果位于医学正常范围内（21-45 天）"

        if isinstance(last_start_date, str):
            last_start = datetime.strptime(last_start_date, "%Y-%m-%d").date()
        else:
            last_start = last_start_date

        next_start = last_start + timedelta(days=int(pred_length))
        ovulation_date = next_start - timedelta(days=14)

        return {
            "last_period_start": last_start.strftime("%Y-%m-%d"),
            "predicted_cycle_length": int(pred_length),
            "raw_predicted_cycle_length": int(raw_pred_length),
            "next_period_start": next_start.strftime("%Y-%m-%d"),
            "next_period_end": (next_start + timedelta(days=4)).strftime("%Y-%m-%d"),
            "ovulation_date": ovulation_date.strftime("%Y-%m-%d"),
            "fertile_window_start": (ovulation_date - timedelta(days=5)).strftime("%Y-%m-%d"),
            "fertile_window_end": (ovulation_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "medical_guardrail_note": medical_note,
            "features_info": f"{MODEL_VERSION} (9维滑动窗口特征)",
        }
