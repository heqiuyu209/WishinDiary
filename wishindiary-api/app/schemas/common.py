"""通用响应/错误 Pydantic 模型。

统一约定：
- 成功响应以 StatusResponse 为基类（status + 可选 message）；
- 错误响应统一为 ErrorResponse（error.code / error.message / error.detail）。
"""

from typing import Any

from pydantic import BaseModel


class StatusResponse(BaseModel):
    """通用成功响应结构。"""

    status: str = "success"
    message: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: Any | None = None


class ErrorResponse(BaseModel):
    """统一错误响应结构（与 app.core.errors 的处理器输出一致）。"""

    error: ErrorDetail
