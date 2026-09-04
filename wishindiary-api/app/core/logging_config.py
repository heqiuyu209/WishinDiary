"""统一日志配置：结构化日志（JSON，生产推荐）与开发可读文本。

默认输出单行 JSON 结构化日志（基于 python-json-logger），统一字段：

    {"ts": <ISO8601>, "level": <LOG LEVEL>, "logger": <logger name>,
     "message": <日志正文>, ...业务/上下文字段}

上下文字段由各中间件/业务代码注入（见 app.core.request_id 与
app.core.metrics），例如 request_id / method / path / status /
duration_ms / client_ip / user_agent 等。

可通过环境变量切换：
    LOG_FORMAT=json   # 生产推荐，单行 JSON，便于 Logstash/Loki/Sentry 采集
    LOG_FORMAT=text   # 本地开发，人类可读文本
    LOG_LEVEL=INFO    # DEBUG | INFO | WARNING | ERROR | CRITICAL

设计约束：
- 日志中绝不写入密码、JWT、Token 或用户日记正文等敏感信息；
- 结构化字段白名单（CONTEXT_FIELDS）之外的 extra 字段默认不输出，
  防止业务代码误把敏感数据带入日志。
"""

import logging
import sys

from pythonjsonlogger import core as _pjl_core
from pythonjsonlogger.json import JsonFormatter

from app.core.config import settings

# 允许进入 JSON 日志的业务/上下文字段白名单
CONTEXT_FIELDS = {
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "client_ip",
    "user_agent",
    "error_code",
    "error_message",
    "metric",
    "pool",
    "model_version",
    "latency_ms",
    "success",
    "user_id",
}

# JsonFormatter 默认排除的标准 logging 字段；此处仅“放行”白名单额外字段与
# level/logger/ts，其余所有 record 属性都会被丢弃。
_RESERVED = [
    attr for attr in _pjl_core.RESERVED_ATTRS if attr not in ("levelname", "name", "timestamp")
]


class _ContextFilter(logging.Filter):
    """把当前请求上下文（request_id 等）注入日志记录的 extra。"""

    def filter(self, record: logging.LogRecord) -> bool:
        # 避免导入环：request_id 模块同样依赖 logging，不依赖本模块
        from app.core.request_id import get_request_id

        request_id = get_request_id()
        if request_id:
            record.request_id = request_id
        else:
            record.request_id = "-"
        return True


def _build_json_formatter() -> logging.Formatter:
    return JsonFormatter(
        rename_fields={
            "levelname": "level",
            "name": "logger",
            "timestamp": "ts",
        },
        reserved_attrs=list(_RESERVED),
        timestamp=True,
        json_ensure_ascii=False,
    )


def _build_text_formatter() -> logging.Formatter:
    return logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(request_id)s %(message)s")


def setup_logging() -> None:
    """配置应用根 logger：统一格式、统一级别，并注入请求上下文。

    幂等：重复调用不会叠加 handler。测试环境（ENVIRONMENT == test）
    不接管 root logger，避免干扰 pytest 的日志收集。
    """
    root = logging.getLogger()
    level_name = settings.LOG_LEVEL.upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    # 避免重复初始化
    for handler in list(root.handlers):
        if getattr(handler, "_wishindiary_configured", False):
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(root.level)
    handler.setFormatter(
        _build_json_formatter() if settings.LOG_FORMAT == "json" else _build_text_formatter()
    )
    handler.addFilter(_ContextFilter())
    handler._wishindiary_configured = True  # type: ignore[attr-defined]
    root.addHandler(handler)
