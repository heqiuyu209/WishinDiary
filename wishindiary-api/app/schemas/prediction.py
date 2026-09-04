from pydantic import BaseModel, Field

class ConfidenceInterval(BaseModel):
    """周期长度预测的不确定性区间（天）。"""
    low: float = Field(..., description="区间下界（5% 分位）")
    high: float = Field(..., description="区间上界（95% 分位）")
    note: str | None = Field(None, description="不确定性说明")

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
    data_quality_warnings: list[str] | None = Field(None, description="数据质量提示（如疑似漏记一次经期开始、周期过短等）")
    features_info: str = Field(..., description="模型特征说明")
    model_version: str = Field(..., description="本次预测所用模型版本")
    confidence_interval: ConfidenceInterval | None = Field(None, description="预测不确定性区间")
    disclaimer: str = Field(..., description="模型使用免责声明")

class PredictionResponse(BaseModel):
    status: str
    prediction: PredictionResponseData | None = None
    message: str | None = None
