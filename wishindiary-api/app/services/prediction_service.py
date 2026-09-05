"""Prediction business logic（周期预测 service 层）。

负责：特征提取 → 模型推理 → 模型监控记录 → 待对账预测写入。
可预期的失败（数据不足）通过返回 insufficient_data 响应表达，
异常由统一异常处理器收敛为 {"error": {...}} 格式。
"""

import logging
import time

from app.core.database import transaction
from app.core.errors import AppError
from app.features import get_latest_features_for_user
from app.repositories.prediction_log_repository import (
    get_existing_pending_prediction,
    insert_pending_prediction,
)
from app.services.cycle_prediction_service import CyclePredictionService

logger = logging.getLogger(__name__)

# 医学合理范围（与特征工程保持一致的宽松口径）
_MIN_PLAUSIBLE_LENGTH = 15
_MAX_PLAUSIBLE_LENGTH = 45
_INSUFFICIENT_DATA_MESSAGE = "数据不足：请至少记录 4 个完整周期后再试"


def build_data_quality_warnings(features: dict) -> list[str]:
    """基于最近 3 条完整周期长度，检测疑似漏记/重复标识的数据质量问题。

    返回可展示给用户的温和提示列表；特征数据无异常时返回空列表。
    - 疑似漏记：某周期长度明显超过常规（>= max(48, 中位数*1.75)），
      对应的实际含义是"再一次经期开始没有被记录"。
    - 疑似重复/过短：某周期长度明显短于常规（<= min(18, 中位数*0.55)）。
    """
    lengths = [
        features.get("lag_1_length"),
        features.get("lag_2_length"),
        features.get("lag_3_length"),
    ]
    lengths = [float(x) for x in lengths if x is not None]
    if len(lengths) < 2:
        return []

    # 基线只取医学合理范围（15-45）内的记录，避免超长间隔污染常规水平；
    # 若合理记录不足，回退到全部样本中位数。
    plausible = [x for x in lengths if _MIN_PLAUSIBLE_LENGTH <= x <= _MAX_PLAUSIBLE_LENGTH]
    import statistics

    baseline = statistics.median(plausible) if plausible else statistics.median(lengths)

    warnings: list[str] = []
    # 超长间隔本身即是"漏记一次开始"的信号，因此不按 45 天上限过滤后再检测
    for length in lengths:
        if length >= max(48.0, baseline * 1.75):
            ratio = length / baseline
            warnings.append(
                f"检测到一段异常长的周期间隔（{int(round(length))} 天，"
                f"约为你常规周期约 {int(round(baseline))} 天的 {ratio:.1f} 倍），"
                "可能漏记了一次经期开始日期，建议核对日历记录。"
            )
            break
    for length in lengths:
        if length <= min(17.0, baseline * 0.6):
            warnings.append(
                f"检测到一段明显过短的周期间隔（{int(round(length))} 天，"
                f"常规周期约 {int(round(baseline))} 天），"
                "可能为重复标记或临时记录异常，建议核对后修正。"
            )
            break
    return warnings


class PredictionService:
    """周期预测业务入口。"""

    def __init__(self, predictor: CyclePredictionService | None = None) -> None:
        # 复用离线预训练模型（应用启动时加载一次，请求时只做推理，不重训）
        self._predictor = predictor or CyclePredictionService()

    def get_prediction(self, user_id: int) -> dict:
        """为用户生成下一次经期预测并记录待对账预测。"""
        try:
            features_dict, last_start_date, n_complete_cycles, user_mean = (
                get_latest_features_for_user(user_id)
            )
        except ValueError:
            # 不把异常文本写入响应；底层异常可能包含实现、路径或数据库细节。
            return {
                "status": "insufficient_data",
                "message": _INSUFFICIENT_DATA_MESSAGE,
                "prediction": None,
            }
        except Exception:
            logger.exception("Feature extraction failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "特征提取失败，请稍后重试")

        # 记录模型推理耗时与成败指标（metric 失败不影响主链路）
        from app.ml.contract import MODEL_VERSION
        from app.core.metrics import record_model_inference

        _infer_start = time.perf_counter()
        prediction_result = self._predictor.predict(
            features_dict,
            last_start_date,
            n_complete_cycles=n_complete_cycles,
            user_mean=user_mean,
        )
        _infer_latency_ms = (time.perf_counter() - _infer_start) * 1000.0
        if prediction_result is None:
            record_model_inference(
                model_version=MODEL_VERSION,
                latency_ms=_infer_latency_ms,
                success=False,
                user_id=user_id,
            )
            raise AppError(500, "internal_error", "预测引擎内部计算错误")
        record_model_inference(
            model_version=MODEL_VERSION,
            latency_ms=_infer_latency_ms,
            success=True,
            user_id=user_id,
        )

        # 记录模型输入分布与预测结果（监控失败不影响主链路）
        try:
            from app.ml.monitoring import record_prediction

            record_prediction(
                user_id=user_id,
                features=features_dict,
                prediction=prediction_result,
                model_version=MODEL_VERSION,
            )
        except Exception:
            logger.exception("模型监控记录失败，忽略", exc_info=True)

        # 记录待对账预测，实际周期开始时由 log_start 回填 actual_date/error_days。
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    pending = get_existing_pending_prediction(
                        cursor, user_id, prediction_result["next_period_start"]
                    )
                    if pending is None:
                        insert_pending_prediction(
                            cursor, user_id, prediction_result["next_period_start"]
                        )
        except Exception:
            logger.exception("prediction log write failed for user_id=%s", user_id)

        # 数据质量提示（疑似漏记/过短间隔），默认无提示
        prediction_result["data_quality_warnings"] = build_data_quality_warnings(features_dict) or None

        return {"status": "success", "prediction": prediction_result}
