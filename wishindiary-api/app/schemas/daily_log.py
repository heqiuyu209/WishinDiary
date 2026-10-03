"""每日健康日志的请求/响应模型。"""

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.common import StatusResponse

# 症状明细：允许的键及默认无症水平（0=无 1=轻 2=中 3=重）
SYMPTOM_KEYS = ("headache", "bloat", "breast_tenderness", "fatigue")
DEFAULT_SYMPTOM_LEVELS = dict.fromkeys(SYMPTOM_KEYS)


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
        if level is not None and (isinstance(level, bool) or not isinstance(level, int) or not (0 <= level <= 3)):
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
    mood_level: int | None = Field(default=None, ge=0, le=3)
    cramps_severity: int | None = Field(default=None, ge=0, le=3)
    is_exercise: bool | None = None
    is_intercourse: bool | None = None
    exercise_type: str | None = Field(default=None, max_length=50)
    exercise_minutes: int | None = Field(default=None, ge=0, le=1440)
    exercise_intensity: int | None = Field(default=None, ge=0, le=3)
    stress_level: int | None = Field(default=None, ge=0, le=3)
    diet_tag: str | None = Field(default=None, max_length=100)
    journal_text: str | None = Field(default=None, max_length=4000)
    # --- 新增自记录维度（睡眠/熬夜、用药、症状明细）---
    sleep_duration_minutes: int | None = Field(default=None, ge=0, le=1440)
    sleep_quality: int | None = Field(default=None, ge=0, le=3)
    sleep_start_minutes: int | None = Field(default=None, ge=0, le=1439)
    is_late_night: bool | None = None
    is_night_shift: bool | None = None
    is_medication: bool | None = None
    medication_note: str | None = Field(default=None, max_length=100)
    symptom_levels: dict[str, int | None] | None = None

    @field_validator("symptom_levels", mode="before")
    @classmethod
    def _validate_symptom_levels(cls, value: dict | None) -> dict:
        return normalize_symptom_levels(value)

    @model_validator(mode="after")
    def validate_exercise(self):
        if self.is_exercise is False:
            if (self.exercise_minutes or 0) > 0 or (self.exercise_intensity or 0) > 0:
                raise ValueError("未运动不能同时填写正数运动时长或强度")
            self.exercise_minutes = 0
            self.exercise_intensity = 0
        return self


class DailyLogRequest(_DailyLogFields):
    """POST /api/v1/daily_log 请求体（幂等 upsert）。"""


class DailyLogUpdateRequest(_DailyLogFields):
    """PUT /api/v1/daily_log 请求体：整体覆盖某天记录（幂等 upsert，语义同 POST）。"""


class DailyLogResponse(StatusResponse):
    """保存每日日志后的响应，包含基于规则的记录提示。"""

    ai_health_advice: list[str]
    advice_source: str = "rule_based"


class DailyLogReadResponse(StatusResponse):
    """GET /api/v1/daily_log 单日查询响应。"""

    log: dict | None = None
