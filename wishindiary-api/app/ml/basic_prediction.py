"""The online cold-start estimator, shared with prospective offline evaluation."""
import statistics
from datetime import timedelta

from app.ml.contract import MODEL_VERSION
from app.ml.prediction_scope import history_is_supported

_DISCLAIMER = (
    "本预测由统计模型生成，仅供参考，不能用于诊断、治疗、避孕或紧急医疗判断。"
    "如有健康疑虑，请咨询专业医疗人员。"
)


def build_basic_prediction(history: list[dict], last_start) -> dict | None:
    """Use only completed history available at the prediction anchor."""
    lengths = [float(r["cycle_length"]) for r in history if r.get("cycle_length") is not None]
    if not lengths or last_start is None or not history_is_supported(history):
        return None

    # This is the model history range, not a medical normality criterion.
    plausible = [x for x in lengths if 15 <= x <= 45.0]
    if plausible:
        personal_mean = sum(plausible) / len(plausible)
        std = statistics.pstdev(plausible) if len(plausible) >= 2 else 0.0
    else:
        personal_mean = lengths[-1]
        std = 0.0

    if hasattr(last_start, "to_pydatetime"):  # MySQL DATE → datetime.date
        last_start = last_start.to_pydatetime().date()

    pred_length = int(round(personal_mean))
    raw_predicted = pred_length
    if not 21 <= pred_length <= 45:
        return None

    next_start = last_start + timedelta(days=pred_length)
    ovulation_date = next_start - timedelta(days=14)

    interval = ({"low": round(pred_length - std, 2), "high": round(pred_length + std, 2),
                 "note": "个人历史均值附近的描述性波动范围，不是经过校准的覆盖保证；样本较少时不确定性仍未知。"}
                if len(plausible) >= 2 and std > 0 else None)

    return {
        "last_period_start": last_start.isoformat(),
        "predicted_cycle_length": pred_length,
        "raw_predicted_cycle_length": raw_predicted,
        "next_period_start": next_start.isoformat(),
        "next_period_end": (next_start + timedelta(days=4)).isoformat(),
        "ovulation_date": ovulation_date.isoformat(),
        "fertile_window_start": (ovulation_date - timedelta(days=5)).isoformat(),
        "fertile_window_end": (ovulation_date + timedelta(days=1)).isoformat(),
        "medical_guardrail_note": (
            f"基于个人经期历史的基础统计量预测（使用 {len(plausible) or len(lengths)} "
            "条完整周期长度）。模型适用范围不代表医学正常范围；不能据此判断身体状态。"
        ),
        "data_quality_warnings": None,
        "features_info": "个人基础统计量模式（数据不足 4 个完整周期时启用）",
        "model_version": MODEL_VERSION,
        "confidence_interval": interval,
        "disclaimer": _DISCLAIMER,
    }
