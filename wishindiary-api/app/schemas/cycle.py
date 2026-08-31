"""Cycle update schemas."""

from pydantic import BaseModel
from datetime import date


class CycleUpdateRequest(BaseModel):
    """更新周期请求体。字段均可选，只更新传入的字段。

    end_date 传 null 表示取消闭合该周期。
    """
    start_date: date | None = None
    end_date: date | None = None
