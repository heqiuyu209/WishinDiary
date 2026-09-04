"""每日健康日志的请求/响应模型。"""

from datetime import date

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.schemas.common import StatusResponse

# 症状明细：允许的键及默认无症水平（0=无 1=轻 2=中 3=重）
SYMPTOM_KEYS = ("headache", "bloat", "breast_tenderness", "fatigue")
DEFAULT_SYMPTOM_LEVELS = {"headache": 0, "bloat": 0, "breast_tenderness": 0, "fatigue": 0}


def normalize_symptom_levels(value: dict | None) -> dict:
    """清洗 symptom_levels：只允许已知键、取值 0~3，缺省键补默认 0。"""
    merged = dict(DEFAULT_SYMPTOM_LEVELS)
    if value is None:
        return merged
    if not isinstance(value, dict):
        raise PydanticCustomError("symptom_levels_invalid", "symptom_levels 必须是对象")
    for key, level in value.items():
        if key not in SYMPTOM_KEYS:
            raise PydanticCustomError(
                "symptom_levels_invalid", "非法症状键: {key}", {"key": key}
            )
        if isinstance(level, bool) or not isinstance(level, int) or not (0 <= level <= 3):
            raise PydanticCustomError(
                "symptom_levels_invalid",
                "症状 {key} 取值须在 0~3",
                {"key": key},
            )
        merged[key] = level
    return merged


class _DailyLogFields(BaseModel):
    """每日日志公共字段（POST 与 PUT 共用的持久化契约）。"""

    log_date: date
    mood_level: int = Field(default=0, ge=0, le=3)
    cramps_severity: int = Field(default=0, ge=0, le=3)
    is_exercise: bool = False
    is_intercourse: bool = False
    exercise_type: str | None = Field(default=None, max_length=50)
    exercise_minutes: int = Field(default=0, ge=0, le=1440)
    diet_tag: str | None = Field(default=None, max_length=100)
    journal_text: str | None = Field(default=None, max_length=4000)
    # --- 新增自记录维度（睡眠/熬夜、用药、症状明细）---
    sleep_duration_minutes: int = Field(default=0, ge=0, le=1440)
    sleep_quality: int = Field(default=0, ge=0, le=3)  # 0=未填/很差 1=差 2=一般 3=好
    is_late_night: bool = False
    is_medication: bool = False
    medication_note: str | None = Field(default=None, max_length=100)
    symptom_levels: dict[str, int] | None = None

    @field_validator("symptom_levels")
    @classmethod
    def _validate_symptom_levels(cls, value: dict | None) -> dict:
        return normalize_symptom_levels(value)


class DailyLogRequest(_DailyLogFields):
    """POST /api/v1/daily_log 请求体（幂等 upsert）。"""


class DailyLogUpdateRequest(_DailyLogFields):
    """PUT /api/v1/daily_log 请求体：整体覆盖某天记录（幂等 upsert，语义同 POST）。"""


class DailyLogResponse(StatusResponse):
    """保存每日日志后的响应，包含 AI 生成的健康建议。"""

    ai_health_advice: list[str]


class DailyLogReadResponse(StatusResponse):
    """GET /api/v1/daily_log 单日查询响应。"""

    log: dict | None = None
