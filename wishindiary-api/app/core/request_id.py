"""Request ID 中间件：为每个请求生成/透传 X-Request-ID 并回传响应头。

用途：
- 链路追踪：前端/网关/日志/告警通过同一 request_id 关联单次请求全链路；
- 安全审计：CSRF 拒绝、限流、异常日志均可携带 request_id 定位问题；
- 透传策略：若上游（网关 / nginx）已传入 X-Request-ID，则原样使用，
  便于跨服务串联；否则生成 UUID4（hex）作为本请求唯一标识。

实现说明：
- 通过 contextvars.ContextVar 将 request_id 注入当前异步上下文，
  logging_config._ContextFilter 会把它写入该请求内产生的所有日志行；
- 响应头统一回传 X-Request-ID，方便 curl / 前端控制台对照日志排查。
"""

import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# 当前请求的 request_id（默认空串，避免未初始化时 KeyError）
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """返回当前请求的 request_id；非请求上下文（如启动脚本）返回空串。"""
    return _request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 透传上游传入的 request_id（网关场景），否则生成新值
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = _request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)
        # 响应头统一回传，便于前端/CLI 对照日志
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
