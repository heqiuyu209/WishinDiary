"""轻量可观测性指标模块：API 耗时/错误率、数据库连接池、模型推理。

指标有两种消费方式（二选一或并存，环境变量 METRICS_ENABLED 控制）：

1. 结构化日志指标（默认启用的日志侧指标）：每个请求结束时输出一条
   `wishindiary.access` 结构化日志，含 method/path/status/duration_ms，
   附带数据库连接池快照；模型推理在服务层调用 record_model_inference()
   输出 `wishindiary.model` 指标日志。可用 Logstash / Loki 等按字段聚合，
   即可得到 API 耗时分布、错误率、池使用率等。

2. Prometheus 文本格式（METRICS_ENABLED=true 时挂载 /metrics）：
   进程内线程安全计数器聚合为 Prometheus 文本格式，由采集器抓取
   （如 Prometheus + Grafana / VictoriaMetrics）。

设计约束：
- 指标采集不得影响主链路：任何异常仅记录，不抛出；
- 路径做基数归一化：路径中的纯数字段替换为 :id，避免高基数标签
  （如 /api/v1/cycles/123 → /api/v1/cycles/:id）。
"""

import logging
import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("wishindiary.access")
model_logger = logging.getLogger("wishindiary.model")

# 进程内指标计数器（Prometheus 文本格式来源）
_lock = Lock()
_http_total: dict[tuple[str, str], int] = defaultdict(int)
_http_errors: dict[tuple[str, str], int] = defaultdict(int)
_http_duration_ms: dict[tuple[str, str], float] = defaultdict(float)
_model_total: dict[str, int] = defaultdict(int)  # model_version -> count
_model_errors: dict[str, int] = defaultdict(int)
_model_duration_ms: dict[str, float] = defaultdict(float)


def _normalize_path(path: str) -> str:
    """路径基数归一化：把纯数字路径段替换为 :id。"""
    return "/".join(":id" if seg.isdigit() else seg for seg in path.split("/"))


class MetricsMiddleware(BaseHTTPMiddleware):
    """采集 API 请求耗时与错误率并输出结构化访问日志。"""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        method = request.method
        normalized = _normalize_path(request.url.path)
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self._record(method, normalized, status, duration_ms)

    @staticmethod
    def _record(method: str, path: str, status: int, duration_ms: float) -> None:
        key = (method, path)
        with _lock:
            _http_total[key] += 1
            _http_duration_ms[key] += duration_ms
            if status >= 500:
                _http_errors[key] += 1

        access_logger.info(
            "http_request",
            extra={
                "metric": "http_request",
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(duration_ms, 3),
                "pool": _pool_snapshot(),
            },
        )


def _pool_snapshot() -> dict[str, int]:
    """读取数据库连接池当前状态（尽力而为，失败不影响主链路）。"""
    try:
        from app.core.database import pool

        in_use = max(0, pool._connections - len(pool._idle_cache))
        return {
            "max_connections": pool._maxconnections,
            "created_connections": pool._connections,
            "idle_connections": len(pool._idle_cache),
            "in_use_connections": in_use,
            "active": len(pool._idle_cache) > 0,
        }
    except Exception:
        return {}


def record_model_inference(
    *,
    model_version: str,
    latency_ms: float,
    success: bool = True,
    user_id: int | None = None,
) -> None:
    """记录一次模型推理的耗时与成败指标（结构化日志指标 + 计数器）。

    在推理主链路调用；内部捕获异常，绝不干扰业务返回。
    """
    try:
        with _lock:
            _model_total[model_version] += 1
            _model_duration_ms[model_version] += max(latency_ms, 0.0)
            if not success:
                _model_errors[model_version] += 1
        model_logger.info(
            "model_inference",
            extra={
                "metric": "model_inference",
                "model_version": model_version,
                "latency_ms": round(max(latency_ms, 0.0), 3),
                "success": success,
                "user_id": user_id,
            },
        )
    except Exception:
        # 指标记录失败绝不阻塞推理链路
        logger.debug("record_model_inference failed", exc_info=True)


def log_pool_metrics() -> None:
    """显式输出一次数据库连接池指标（供定时任务 / 运维手动触发）。"""
    pool = _pool_snapshot()
    if pool:
        logger.info("db_pool_metrics", extra={"metric": "db_pool", "pool": pool})


# ---------------------------------------------------------------------------
# Prometheus 文本格式暴露（METRICS_ENABLED=true 时由 main.py 挂载 /metrics）
# ---------------------------------------------------------------------------


def render_metrics() -> str:
    """把进程内计数器渲染为 Prometheus 文本格式。"""
    lines: list[str] = [
        "# HELP wishindiary_http_requests_total 处理的总请求数（按 method+path）",
        "# TYPE wishindiary_http_requests_total counter",
    ]
    with _lock:
        for (method, path), value in sorted(_http_total.items()):
            lines.append(
                f'wishindiary_http_requests_total{{method="{method}",path="{path}"}} {value}'
            )
        lines += [
            "# HELP wishindiary_http_errors_total 5xx 错误请求数（按 method+path）",
            "# TYPE wishindiary_http_errors_total counter",
        ]
        for (method, path), value in sorted(_http_errors.items()):
            lines.append(
                f'wishindiary_http_errors_total{{method="{method}",path="{path}"}} {value}'
            )
        lines += [
            "# HELP wishindiary_http_duration_ms_total 请求总耗时（毫秒，按 method+path）",
            "# TYPE wishindiary_http_duration_ms_total counter",
        ]
        for (method, path), value in sorted(_http_duration_ms.items()):
            lines.append(
                f'wishindiary_http_duration_ms_total{{method="{method}",path="{path}"}} {value}'
            )

        pool = _pool_snapshot()
        lines += [
            "# HELP wishindiary_db_pool_max_connections 连接池最大连接数",
            "# TYPE wishindiary_db_pool_max_connections gauge",
            f"wishindiary_db_pool_max_connections {pool.get('max_connections', 0)}",
            "# HELP wishindiary_db_pool_created_connections 已创建的连接数",
            "# TYPE wishindiary_db_pool_created_connections gauge",
            f"wishindiary_db_pool_created_connections {pool.get('created_connections', 0)}",
            "# HELP wishindiary_db_pool_idle_connections 空闲连接数",
            "# TYPE wishindiary_db_pool_idle_connections gauge",
            f"wishindiary_db_pool_idle_connections {pool.get('idle_connections', 0)}",
            "# HELP wishindiary_db_pool_in_use_connections 使用中的连接数",
            "# TYPE wishindiary_db_pool_in_use_connections gauge",
            f"wishindiary_db_pool_in_use_connections {pool.get('in_use_connections', 0)}",
        ]

        lines += [
            "# HELP wishindiary_model_inference_total 模型推理总次数（按 model_version）",
            "# TYPE wishindiary_model_inference_total counter",
        ]
        for ver, value in sorted(_model_total.items()):
            lines.append(f'wishindiary_model_inference_total{{model_version="{ver}"}} {value}')
        lines += [
            "# HELP wishindiary_model_inference_errors_total 模型推理失败次数",
            "# TYPE wishindiary_model_inference_errors_total counter",
        ]
        for ver, value in sorted(_model_errors.items()):
            lines.append(
                f'wishindiary_model_inference_errors_total{{model_version="{ver}"}} {value}'
            )
        lines += [
            "# HELP wishindiary_model_inference_duration_ms_total 模型推理总耗时（毫秒）",
            "# TYPE wishindiary_model_inference_duration_ms_total counter",
        ]
        for ver, value in sorted(_model_duration_ms.items()):
            lines.append(
                f'wishindiary_model_inference_duration_ms_total{{model_version="{ver}"}} {round(value, 3)}'
            )
    return "\n".join(lines) + "\n"


def metrics_endpoint(request: Request) -> JSONResponse:
    """/metrics 端点：返回 Prometheus 文本格式。"""
    _ = request
    return JSONResponse(
        content=render_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
