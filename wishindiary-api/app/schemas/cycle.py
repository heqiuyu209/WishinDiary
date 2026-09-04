"""Cycle schemas（周期模块请求/响应模型）。"""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import StatusResponse


class LogStartRequest(BaseModel):
    """标记周期开始请求。"""

    start_date: date


class LogEndRequest(BaseModel):
    """标记周期结束请求。"""

    end_date: date
    cycle_id: int | None = Field(default=None, description="可选：指定要修正的历史周期")


class CycleUpdateRequest(BaseModel):
    """更新周期请求体。字段均可选，只更新传入的字段。

    end_date 传 null 表示取消闭合该周期。
    """
    start_date: date | None = None
    end_date: date | None = None


class CycleOperationResponse(StatusResponse):
    """周期写入操作（开始/结束/更新/删除）的统一响应。"""
