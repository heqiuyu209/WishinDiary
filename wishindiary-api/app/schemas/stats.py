"""仪表盘统计接口的响应模型。"""

from datetime import date

from pydantic import BaseModel

from app.schemas.common import StatusResponse


class CycleRead(BaseModel):
    """周期记录（只读视图）。"""

    cycle_id: int
    start_date: date
    end_date: date | None = None
    cycle_length: int | None = None
    bleeding_days: int | None = None


class DailyLogSummary(BaseModel):
    """每日日志摘要（列表视图）。"""

    log_date: date
    mood_level: int
    cramps_severity: int
    is_exercise: bool
    exercise_type: str | None = None
    journal_text: str | None = None


class StatsResponse(StatusResponse):
    cycles: list[CycleRead]
    recent_logs: list[DailyLogSummary]
