"""Model applicability is separate from observation storage and medical status."""

import math

SCOPE_MESSAGE = "近期记录超出当前模型的历史适用范围（15–45 天），暂不提供预计日期。请核对漏记或补录；真实长间隔仍会保留。此判断不代表医学诊断。"


class PredictionScopeError(ValueError):
    pass


def history_is_supported(history: list[dict]) -> bool:
    lengths = [float(row["cycle_length"]) for row in history if row.get("cycle_length") is not None]
    return all(math.isfinite(value) and 15 <= value <= 45 for value in lengths[-3:])
