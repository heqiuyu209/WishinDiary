"""统一 API 错误响应结构与全局异常处理。

全应用统一的错误响应格式（对 /api/v1 下所有接口生效）：

    {"error": {"code": <机器可读错误码>, "message": <人类可读消息>, "detail": <额外细节或 null>}}

设计约定：
- 业务层可预期的失败通过抛出 AppError（携带 status_code / code / message / detail）
  表达，由全局处理器收敛为上述结构；
- 框架抛出的 HTTPException（如 401/404/429）由处理器按状态码映射错误码；
- Pydantic 校验失败（422）与未预期异常（500）同样收敛为统一结构，
  保证全接口错误响应一致、前端可按统一契约解析。
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """业务可预期错误：携带 HTTP 状态码、机器可读错误码与人类可读消息。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Any = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


_STATUS_CODE_MAP = {
    400: "invalid_input",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def _code_for_status(status_code: int) -> str:
    return _STATUS_CODE_MAP.get(status_code, "http_error")


def _error_body(code: str, message: str, detail: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail}}


def register_exception_handlers(app: FastAPI) -> None:
    """把各类异常统一收敛为 {"error": {"code", "message", "detail"}} 结构。"""

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                _code_for_status(exc.status_code),
                str(exc.detail),
                None,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "validation_error",
                "请求参数校验失败",
                exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "服务器内部错误", None),
        )
