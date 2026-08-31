from pydantic import BaseModel, Field

class PredictionResponseData(BaseModel):
    last_period_start: str = Field(..., description="上次经期开始日期 (YYYY-MM-DD)")
    predicted_cycle_length: int = Field(..., description="预估周期长度")
    raw_predicted_cycle_length: int | None = Field(None, description="模型原始输出的周期长度（未做医学边界修正）")
    next_period_start: str = Field(..., description="预测下次开始日期")
    next_period_end: str = Field(..., description="预测下次结束日期")
    ovulation_date: str = Field(..., description="排卵日")
    fertile_window_start: str = Field(..., description="易孕期开始")
    fertile_window_end: str = Field(..., description="易孕期结束")
    medical_guardrail_note: str | None = Field(None, description="医学边界修正说明")
    features_info: str = Field(..., description="模型特征说明")

class PredictionResponse(BaseModel):
    status: str
    prediction: PredictionResponseData | None = None
    message: str | None = None
