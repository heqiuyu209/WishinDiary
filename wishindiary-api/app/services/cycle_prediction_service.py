"""Cycle prediction inference service.

使用离线预训练的随机森林模型进行推理（不在请求时训练）。
模型由 `scripts/train.py` 离线训练并保存为 skops，特征口径与训练一致：
    10 个滑动窗口特征 (lag_1~3_length, lag_1~3_bleeding, roll_3_mean, roll_3_std,
                       start_month_sin, start_month_cos)
预测链路在全局 RF 输出之上叠加贝叶斯收缩个性化（P0-2）：
    final = w * global_pred + (1 - w) * user_mean，其中 w = 1 / (1 + n_complete_cycles / K)，K=4。
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

    # P0-2 贝叶斯收缩的超参数：个人均值与全局预测各占一半需要的历史周期数。
    # w = 1 / (1 + n / K)，n 为用户完整周期数（样本越多越信任个人均值）。
    SHRINKAGE_K = 4.0

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

    def predict(
        self,
        features_dict: dict,
        last_start_date,
        n_complete_cycles: int | None = None,
        user_mean: float | None = None,
    ) -> dict | None:
        """用 10 特征 + 上次经期开始日期推理下一次经期（含贝叶斯收缩个性化）。

        features_dict: 与 FEATURE_NAMES 完全对应的 10 个特征值
        last_start_date: 用户最近一次经期开始日期 (date)
        n_complete_cycles / user_mean: 个人完整周期数与未收缩周期长度均值（P0-2 个性化先验）；
            缺省或历史不足时回退为纯全局预测（w = 1，兼容旧调用方）。
        """
        try:
            row = [float(features_dict[name]) for name in FEATURE_NAMES]
            if self.model is None and settings.ENVIRONMENT == "production":
                logger.error("生产环境模型未加载，拒绝提供基线预测")
                return None
            if self.model is None:
                raw_model_length = float(features_dict["roll_3_mean"])
            else:
                # 按模型训练口径自适应：带特征名(新脚本训练)传 DataFrame，
                # 无特征名(旧模型)传 NumPy，双向兼容即可彻底消除 feature-names 警告。
                trained_names = getattr(self.model, "feature_names_in_", None)
                if trained_names is not None:
                    import pandas as pd

                    x_input = pd.DataFrame([row], columns=list(trained_names))
                else:
                    import numpy as np

                    x_input = np.array([row], dtype=float)
                raw_model_length = float(self.model.predict(x_input)[0])
        except (KeyError, TypeError, ValueError):
            logger.exception("推理输入无效")
            return None

        # P0-2 贝叶斯收缩个性化：
        #   final = w * global_pred + (1 - w) * user_mean,  w = 1 / (1 + n_complete_cycles / K)
        # K = SHRINKAGE_K（默认 4）。n_complete_cycles 越大越信任个人均值；
        # 历史不足（None 或 <1，或 user_mean 无效）时回退纯全局预测（w = 1）。
        shrinkage = self._compute_shrinkage(n_complete_cycles, user_mean)
        if shrinkage is not None:
            w, user_mean_used = shrinkage
            adjusted_model_length = w * raw_model_length + (1.0 - w) * user_mean_used
        else:
            adjusted_model_length = raw_model_length

        # raw_predicted_cycle_length 保持"全局模型原始输出"语义（不掺收缩），
        # 供监控一致性/衰减分析使用；对外业务结果用收缩后的 adjusted 值。
        raw_pred_length = int(round(raw_model_length))
        pred_round = int(round(adjusted_model_length))

        # 医学边界保护（基于收缩后的最终预测值）
        pred_length = max(21, min(pred_round, 45))
        if pred_round != pred_length:
            medical_note = (
                f"模型收缩后输出 {pred_round} 天，已按医学边界修正为 {pred_length} 天（21-45 天）"
            )
        else:
            medical_note = "预测结果位于医学正常范围内（21-45 天，已含个人历史收缩）"

        # 不确定性区间：基于随机森林各树预测分布的分位数（5%~95%）。
        # 各树预测同样按相同收缩权重混入个人均值，保证 CI 与收缩后语义一致。
        confidence_interval = self._compute_confidence_interval(row, shrinkage)

        if isinstance(last_start_date, str):
            last_start = datetime.strptime(last_start_date, "%Y-%m-%d").date()
        else:
            last_start = last_start_date

        next_start = last_start + timedelta(days=int(pred_length))
        ovulation_date = next_start - timedelta(days=14)

        return {
            "last_period_start": last_start.strftime("%Y-%m-%d"),
            "predicted_cycle_length": int(pred_length),
            "raw_predicted_cycle_length": raw_pred_length,
            "next_period_start": next_start.strftime("%Y-%m-%d"),
            "next_period_end": (next_start + timedelta(days=4)).strftime("%Y-%m-%d"),
            "ovulation_date": ovulation_date.strftime("%Y-%m-%d"),
            "fertile_window_start": (ovulation_date - timedelta(days=5)).strftime("%Y-%m-%d"),
            "fertile_window_end": (ovulation_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            "medical_guardrail_note": medical_note,
            "features_info": f"{MODEL_VERSION} (10维滑动窗口特征)",
            "model_version": MODEL_VERSION,
            "confidence_interval": confidence_interval,
            "disclaimer": (
                "本预测由统计模型生成，仅供参考，不能用于诊断、治疗、避孕或紧急医疗判断。"
                "如有健康疑虑，请咨询专业医疗人员。"
            ),
        }

    @staticmethod
    def _compute_shrinkage(
        n_complete_cycles: int | None, user_mean: float | None
    ) -> tuple[float, float] | None:
        """贝叶斯收缩个性化权重（P0-2）。

        公式：final = w * global_pred + (1 - w) * user_mean，w = 1 / (1 + n_complete_cycles / K)。
        返回 (w, user_mean)；当历史不足（无完整周期 / 均值无效）时返回 None 表示回退纯全局预测。
        user_mean 为未收缩的原始周期长度均值，仅在收缩时被加权使用。
        """
        if n_complete_cycles is None or user_mean is None:
            return None
        if n_complete_cycles < 1 or float(user_mean) <= 0:
            return None
        w = 1.0 / (1.0 + float(n_complete_cycles) / CyclePredictionService.SHRINKAGE_K)
        return (w, float(user_mean))

    def _compute_confidence_interval(
        self, row: list[float], shrinkage: tuple[float, float] | None = None
    ) -> dict | None:
        """根据随机森林各决策树的预测分布给出 5%~95% 不确定性区间。

        传入 shrinkage (w, user_mean) 时，各树预测同样按 w*tree + (1-w)*user_mean 收缩，
        使 CI 与最终收缩后预测的语义一致（P0-2）。
        """
        if self.model is None:
            return None
        try:
            estimators = getattr(self.model, "estimators_", None)
            if not estimators:
                return None
            import numpy as np

            # 注意：RF 顶层带 feature_names_in_，但其内部各棵 DecisionTree 通常不带
            # （sklearn 拟合时树只收到 NumPy）。此处按树的训练口径自适应，
            # 避免对 200 棵树逐棵 predict 时刷 feature-names 警告。
            trained_names = getattr(estimators[0], "feature_names_in_", None)
            if trained_names is not None:
                import pandas as pd

                base = pd.DataFrame([row], columns=list(trained_names))
            else:
                base = np.array([row], dtype=float)
            tree_preds = np.array([tree.predict(base)[0] for tree in estimators])
            if shrinkage is not None:
                w, user_mean_used = shrinkage
                tree_preds = w * tree_preds + (1.0 - w) * user_mean_used
            low, high = float(np.percentile(tree_preds, 5)), float(np.percentile(tree_preds, 95))
            note = "基于随机森林各树预测分布的 5%~95% 分位，衡量模型不确定性"
            if shrinkage is not None:
                note += "（已按个人历史收缩）"
            note += "。"
            return {
                "low": round(low, 2),
                "high": round(high, 2),
                "note": note,
            }
        except Exception:
            logger.exception("计算预测置信区间失败，忽略该字段")
            return None
