"""Sentry 最小可用接入：错误上报 + 性能追踪，环境变量可开关。

启用条件（全部满足才初始化）：
- SENTRY_DSN 非空（.env 中配置，生产建议开启）；
- ENVIRONMENT != "test"（测试环境绝不初始化，避免干扰单测）。

关闭方式：
- 将 SENTRY_DSN 留空即可完全禁用（默认）。

说明：Sentry 会通过 sentry_sdk 的 FastAPI/Starlette 集成自动捕获未处理
异常并上报；性能追踪采样率由 SENTRY_TRACES_SAMPLE_RATE 控制。日志中
包含的 request_id 会随 Sentry 上下文一并上报，便于在 Sentry 面板按
request_id 检索（通过 before_send / tags 关联）。
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """初始化 Sentry；未配置 DSN 或测试环境时直接跳过。返回是否启用。"""
    if not settings.SENTRY_DSN:
        return False
    if settings.ENVIRONMENT == "test":
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_logging = LoggingIntegration(
            level=logging.INFO,  # 捕获 >= INFO 的日志事件
            event_level=logging.ERROR,  # ERROR 及以上作为 event 上报
        )
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,  # 不上报用户 PII，保护健康数据
            integrations=[
                sentry_logging,
                StarletteIntegration(),
                FastApiIntegration(),
            ],
            # 附加 request_id，便于按链路检索
            before_send=lambda event, hint: _attach_request_id(event),
        )
        logger.info("Sentry 已启用（environment=%s）", settings.ENVIRONMENT)
        return True
    except Exception:
        logger.exception("Sentry 初始化失败，应用将继续运行（不阻断启动）")
        return False


def _attach_request_id(event):
    """把当前请求的 request_id 写入 Sentry 事件的 tags。"""
    try:
        from app.core.request_id import get_request_id

        request_id = get_request_id()
        if request_id:
            event.setdefault("tags", {})["request_id"] = request_id
    except Exception:
        pass
    return event
