"""基于 Origin/Referer 校验的 CSRF 防护中间件。

背景：认证凭据放在 HttpOnly Cookie（SameSite=Lax）。现代浏览器对
SameSite=Lax 的 Cookie 在跨站 POST 请求中默认不携带，但为了纵深防御
（例如旧浏览器、浏览器降级、iframe 内嵌等），对「携带 access_token
Cookie 的非安全方法」额外校验请求来源是否被信任。

判定规则（任一命中即放行）：
1. Origin 头存在且在 CORS 白名单内（或与当前 Host 同源）；
2. Origin 缺失时回退校验 Referer；
3. Origin 与 Referer 均缺失（如 curl / 脚本 / 服务端调用），
   判定为非浏览器请求，放行并记录告警日志。

该中间件不会拦截未携带认证 Cookie 的请求，因此不影响公开接口。
"""

import logging
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
COOKIE_NAME = "access_token"


class CSRFSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS or COOKIE_NAME not in request.cookies:
            return await call_next(request)

        if not self._is_trusted_source(request):
            logger.warning(
                "CSRF 校验失败：method=%s path=%s origin=%s referer=%s",
                request.method,
                request.url.path,
                request.headers.get("origin", ""),
                request.headers.get("referer", ""),
            )
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "forbidden", "message": "CSRF 校验失败：请求来源不被信任", "detail": None}},
            )
        return await call_next(request)

    @staticmethod
    def _is_trusted_source(request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin:
            return CSRFSecurityMiddleware._origin_allowed(origin, request)

        referer = request.headers.get("referer")
        if referer:
            try:
                parsed = urlparse(referer)
                candidate = f"{parsed.scheme}://{parsed.netloc}"
                return CSRFSecurityMiddleware._origin_allowed(candidate, request)
            except Exception:
                logger.exception("无法解析 Referer: %s", referer)
                return False

        # 无 Origin 且无 Referer：判定为非浏览器客户端（curl/脚本），放行。
        logger.warning(
            "跨域防护：请求缺少 Origin/Referer，按非浏览器客户端处理 path=%s",
            request.url.path,
        )
        return True

    @staticmethod
    def _origin_allowed(origin: str, request: Request) -> bool:
        try:
            parsed = urlparse(origin)
            netloc = parsed.netloc
        except Exception:
            return False
        allowed_origins = settings.cors_origins
        for allowed in allowed_origins:
            try:
                if urlparse(allowed).netloc == netloc:
                    return True
            except Exception:
                continue
        # 同源放行：Origin 的 host 与当前请求 Host 一致
        current_host = request.headers.get("host", "")
        return netloc == current_host
