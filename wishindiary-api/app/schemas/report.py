"""健康报告接口的响应模型。"""

from pydantic import BaseModel

from app.schemas.common import StatusResponse


class ReportData(BaseModel):
    average_cycle_length: float
    ai_prediction_accuracy_days: float | str
    total_recorded_cycles: int
    cramps_evaluation: str
    doctor_advice_summary: str
    cycle_regularity: str = ""
    data_readiness: str = ""
    cycle_length_hint: str = ""
    latest_prediction_error_days: float | None = None
    disclaimer: str


class ReportResponse(StatusResponse):
    report: ReportData
