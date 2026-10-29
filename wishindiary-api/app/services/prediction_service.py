"""Prediction business logic（周期预测 service 层）。

负责：特征提取 → 模型推理 → 模型监控记录 → 待对账预测写入。
可预期的失败（数据不足）通过返回 insufficient_data 响应表达，
异常由统一异常处理器收敛为 {"error": {...}} 格式。

数据门槛（B 任务）：
- 完整周期 >= 4：走离线 ML 模型 + 贝叶斯收缩个性化；
- 完整周期 1~3（含新用户注册补录的 >=2 个经期开始日）：降级为
  个人基础统计量预测，新用户即刻获得可用统计量与预测区间；
- 无任何完整周期：维持 insufficient_data 响应。
"""

import logging
import statistics
import time

from app.core.database import transaction
from app.core.errors import AppError
from app.features import get_latest_features_for_user
from app.ml.basic_prediction import build_basic_prediction
from app.ml.contract import MODEL_VERSION
from app.repositories.cycle_repository import (
    get_recent_cycle_lengths,
    get_user_latest_cycle,
    get_user_valid_cycles,
)
from app.repositories.prediction_log_repository import (
    insert_prediction_snapshot,
)
from app.services.cycle_prediction_service import CyclePredictionService

logger = logging.getLogger(__name__)

# 医学合理范围（与特征工程保持一致的宽松口径）
_MIN_PLAUSIBLE_LENGTH = 15
_MAX_PLAUSIBLE_LENGTH = 45
_INSUFFICIENT_DATA_MESSAGE = "数据不足：请至少记录 4 个完整周期后再试"

def build_data_quality_warnings(features: dict) -> list[str]:
    """基于最近 3 条原始周期间隔，检测疑似漏记/重复标识的数据质量问题。

    返回可展示给用户的温和提示列表；特征数据无异常时返回空列表。
    - 疑似漏记：某周期长度明显超过常规（>= max(48, 中位数*1.75)），
      对应的实际含义是"再一次经期开始没有被记录"。
    - 疑似重复/过短：某周期长度明显短于常规（<= min(17, 中位数*0.6)）。
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


def get_data_quality_warnings(user_id: int) -> list[str]:
    """Keep quality checks independent of the model's filtered lag features."""
    try:
        with transaction() as connection:
            with connection.cursor() as cursor:
                rows = get_recent_cycle_lengths(cursor, user_id)
        return build_data_quality_warnings({
            f"lag_{index}_length": row["cycle_length"]
            for index, row in enumerate(rows, 1)
        })
    except Exception:
        logger.exception("Data quality query failed for user_id=%s", user_id)
        raise AppError(500, "internal_error", "数据质量检查失败，请稍后重试")


def build_basic_stats_prediction(user_id: int) -> dict | None:
    """完整周期不足 4 个时的降级预测：基于个人完整周期长度的基础统计量。

    返回 None 表示该用户连 1 个完整周期都没有（维持原 insufficient_data 语义）。
    该模式服务于新用户注册补录经期开始日期的场景：只要补录 >=2 个日期
    （至少 1 个完整周期），即可立即获得可用统计量、预测起点与区间。
    """
    try:
        with transaction() as connection:
            with connection.cursor() as cursor:
                rows = get_user_valid_cycles(cursor, user_id) or []
                latest = get_user_latest_cycle(cursor, user_id)
    except Exception:
        logger.exception("basic stats prediction query failed for user_id=%s", user_id)
        raise AppError(500, "internal_error", "特征提取失败，请稍后重试")

    return build_basic_prediction(rows, latest["start_date"] if latest else None)


class PredictionService:
    """周期预测业务入口。"""

    def __init__(self, predictor: CyclePredictionService | None = None) -> None:
        # 复用离线预训练模型（应用启动时加载一次，请求时只做推理，不重训）
        self._predictor = predictor or CyclePredictionService()

    def get_prediction(self, user_id: int, *, record: bool = True) -> dict:
        """为用户生成下一次经期预测并记录待对账预测。

        数据门槛：
        - 完整周期 >= 4：离线 ML 模型 + 贝叶斯收缩；
        - 完整周期 1~3（含注册补录 >=2 个经期开始日的场景）：降级为基础统计量预测，
          新用户无需等到积累满 4 个完整周期即可获得可用预测区间；
        - 无任何完整周期：维持 insufficient_data。
        """
        features_dict = None
        prediction_result = None
        try:
            features_dict, last_start_date, n_complete_cycles, user_mean = (
                get_latest_features_for_user(user_id)
            )
        except ValueError:
            # 完整周期不足 4 个（无法构造 ML 特征窗口）→ 降级为个人基础统计量预测
            prediction_result = build_basic_stats_prediction(user_id)
            if prediction_result is None:
                # 不把异常文本写入响应；底层细节可能包含实现或数据库信息。
                return {
                    "status": "insufficient_data",
                    "message": _INSUFFICIENT_DATA_MESSAGE,
                    "prediction": None,
                }
        except Exception:
            logger.exception("Feature extraction failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "特征提取失败，请稍后重试")

        # 记录模型推理耗时与成败指标（metric 失败不影响主链路）
        from app.core.metrics import record_model_inference

        if prediction_result is None:
            _infer_start = time.perf_counter()
            prediction_result = self._predictor.predict(
                features_dict,
                last_start_date,
                n_complete_cycles=n_complete_cycles,
                user_mean=user_mean,
            )
            _infer_latency_ms = (time.perf_counter() - _infer_start) * 1000.0
            if prediction_result is None:
                if record:
                    record_model_inference(
                        model_version=MODEL_VERSION,
                        latency_ms=_infer_latency_ms,
                        success=False,
                        user_id=user_id,
                    )
                raise AppError(500, "internal_error", "预测引擎内部计算错误")
            if record:
                record_model_inference(
                    model_version=MODEL_VERSION,
                    latency_ms=_infer_latency_ms,
                    success=True,
                    user_id=user_id,
                )

            # 记录模型输入分布与预测结果（监控失败不影响主链路）
            try:
                from app.ml.monitoring import record_prediction

                if record:
                    record_prediction(
                        user_id=user_id,
                        features=features_dict,
                        prediction=prediction_result,
                        model_version=MODEL_VERSION,
                    )
            except Exception:
                logger.exception("模型监控记录失败，忽略", exc_info=True)

        else:
            # 基础统计降级模式：样本过少，跳过模型监控，仅记录推理指标。
            if record:
                try:
                    record_model_inference(
                        model_version=MODEL_VERSION,
                        latency_ms=0.0,
                        success=True,
                        user_id=user_id,
                    )
                except Exception:
                    logger.exception("基础统计预测指标记录失败，忽略")

        # Inspect raw recent intervals for both ML and cold-start predictions.
        prediction_result["data_quality_warnings"] = get_data_quality_warnings(user_id) or None

        # 批处理预览不写预测日志或监控文件；交互式预测保持原行为。
        if not record:
            return {"status": "success", "prediction": prediction_result}

        # 记录待对账预测，实际周期开始时由 log_start 回填 actual_date/error_days。
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    insert_prediction_snapshot(
                        cursor, user_id, prediction_result,
                        method=("basic_stats" if features_dict is None else
                                "rf_personalized" if self._predictor.model is not None else
                                "mean_personalized"),
                        model_sha256=getattr(self._predictor, "model_sha256", None)
                        if features_dict is not None else None,
                    )
        except Exception:
            logger.exception("prediction log write failed for user_id=%s", user_id)

        return {"status": "success", "prediction": prediction_result}
