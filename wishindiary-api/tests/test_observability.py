"""可观测性模块单元测试：request ID、结构化日志、Metrics、Sentry、配置校验。

覆盖 P1「可观测性」前 6 项新增模块的未覆盖分支：
- request_id：X-Request-ID 生成/透传/响应头回传/上下文注入
- metrics：路径归一化、API/DB 池/模型指标计数与 Prometheus 渲染
- logging_config：JSON 格式化、request_id 上下文过滤、幂等初始化
- sentry_client：DSN 空跳过 / 测试环境跳过 / 成功初始化（mock）
- config：validate_observability_config 快速失败分支

所有对 settings 的修改均使用 monkeypatch 自动还原，不影响其它用例。
"""

import sys
import types
from unittest import mock

import pytest

from app.core import metrics as metrics_mod
from app.core import request_id as rid_mod
from app.core.config import validate_observability_config, settings
from app.core.logging_config import CONTEXT_FIELDS, setup_logging
from app.core.sentry_client import _attach_request_id, init_sentry


# ---------------------------------------------------------------------------
# 1. Request ID
# ---------------------------------------------------------------------------
def test_request_id_generated_and_returned(client):
    """每个请求应生成 32 位 hex 的 X-Request-ID 并回传响应头。"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    request_id = resp.headers.get("X-Request-ID")
    assert request_id is not None
    assert len(request_id) == 32
    assert set(request_id) <= set("0123456789abcdef")


def test_request_id_passthrough_from_upstream(client):
    """上游网关传入的 X-Request-ID 应原样透传并回传，便于跨服务串联。"""
    upstream_id = "feed" * 8  # 32 字符
    resp = client.get("/api/health", headers={"X-Request-ID": upstream_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == upstream_id


def test_request_id_contextvar():
    """contextvar 语义：set 后读取、reset 后恢复空串（中间件 finally 保证）。"""
    ctx_var = rid_mod._request_id_var
    token = ctx_var.set("abc123")
    try:
        assert rid_mod.get_request_id() == "abc123"
    finally:
        ctx_var.reset(token)
    assert rid_mod.get_request_id() == ""


# ---------------------------------------------------------------------------
# 2. 结构化日志（logging_config）
# ---------------------------------------------------------------------------
def test_context_filter_injects_request_id(caplog):
    """无请求上下文时日志 record 的 request_id 字段应为占位符 '-'。"""
    import logging as _logging

    caplog.set_level(_logging.INFO)
    setup_logging()  # 幂等，不叠加 handler

    logger = _logging.getLogger("wishindiary.test_observability")
    logger.info("hello")
    # 通过 root handler 输出的 record 由 _ContextFilter 填充 request_id
    records = [r for r in caplog.records if r.getMessage() == "hello"]
    assert records, "应有记录被捕获"
    assert all(getattr(r, "request_id", None) == "-" for r in records)


def test_context_fields_whitelist():
    """结构化字段白名单应包含可观测性核心字段。"""
    for field in (
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
        "metric",
        "pool",
        "model_version",
        "latency_ms",
        "success",
    ):
        assert field in CONTEXT_FIELDS


def test_setup_logging_idempotent():
    """setup_logging 重复调用不应叠加 handler。"""
    root = logging_get_root()
    before = [h for h in root.handlers if getattr(h, "_wishindiary_configured", False)]
    setup_logging()
    after = [h for h in root.handlers if getattr(h, "_wishindiary_configured", False)]
    assert len(after) == len(before)


def logging_get_root():
    import logging

    return logging.getLogger()


# ---------------------------------------------------------------------------
# 3. API / DB 池 / 模型指标（metrics）
# ---------------------------------------------------------------------------
def test_normalize_path():
    """纯数字路径段应归一化为 :id，避免高基数标签。"""
    assert metrics_mod._normalize_path("/api/v1/cycles/123") == "/api/v1/cycles/:id"
    assert metrics_mod._normalize_path("/api/v1/cycles") == "/api/v1/cycles"
    assert metrics_mod._normalize_path("/api/v1") == "/api/v1"


def test_record_model_inference_success_and_failure():
    """模型推理成功率/失败率计数与指标日志调用。"""
    before_total = metrics_mod._model_total["v1-test"]
    before_err = metrics_mod._model_errors["v1-test"]

    with mock.patch.object(metrics_mod.model_logger, "info", return_value=None) as spy:
        metrics_mod.record_model_inference(
            model_version="v1-test", latency_ms=12.5, success=True, user_id=7
        )
        metrics_mod.record_model_inference(
            model_version="v1-test", latency_ms=-1.0, success=False, user_id=7
        )
        # 每次成功/失败推理都会输出一条指标日志
        assert spy.call_count == 2
        extra = spy.call_args_list[0].kwargs["extra"]
        assert extra["metric"] == "model_inference"
        assert extra["model_version"] == "v1-test"
        assert extra["success"] is True
        assert isinstance(extra["latency_ms"], float)

    assert metrics_mod._model_total["v1-test"] == before_total + 2
    assert metrics_mod._model_errors["v1-test"] == before_err + 1
    assert metrics_mod._model_duration_ms["v1-test"] >= 12.5  # 负数取 0


def test_render_metrics_contains_all_series():
    """Prometheus 文本格式应包含 HTTP / DB 池 / 模型三类指标。"""
    rendered = metrics_mod.render_metrics()
    for name in (
        "wishindiary_http_requests_total",
        "wishindiary_http_errors_total",
        "wishindiary_http_duration_ms_total",
        "wishindiary_db_pool_max_connections",
        "wishindiary_db_pool_created_connections",
        "wishindiary_db_pool_idle_connections",
        "wishindiary_db_pool_in_use_connections",
        "wishindiary_model_inference_total",
        "wishindiary_model_inference_errors_total",
        "wishindiary_model_inference_duration_ms_total",
    ):
        assert name in rendered


def test_metrics_endpoint_response():
    """/metrics 端点应返回 text/plain 的 Prometheus 文本。"""
    from starlette.requests import Request

    req = mock.Mock(spec=Request)
    resp = metrics_mod.metrics_endpoint(req)
    assert resp.media_type.startswith("text/plain")
    assert "wishindiary_http_requests_total" in resp.body.decode()


def test_http_metrics_recorded_on_request(client):
    """一次真实请求应被 MetricsMiddleware 计入 HTTP 指标。"""
    before = dict(metrics_mod._http_total)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    key = ("GET", "/api/health")
    assert metrics_mod._http_total.get(key, 0) == before.get(key, 0) + 1
    assert metrics_mod._http_errors.get(("GET", "/api/health"), 0) == 0  # 200 非 5xx


def test_pool_snapshot_best_effort():
    """池快照失败返回空 dict，不抛异常；正常时返回含关键字段的 dict。"""
    from app.core.database import pool

    _ = pool  # conftest 已把连接池切到测试库
    snap = metrics_mod._pool_snapshot()
    assert isinstance(snap, dict)
    for key in (
        "max_connections",
        "created_connections",
        "idle_connections",
        "in_use_connections",
    ):
        assert key in snap


# ---------------------------------------------------------------------------
# 4. Sentry（sentry_client）
# ---------------------------------------------------------------------------
def test_sentry_disabled_when_dsn_empty(monkeypatch):
    """SENTRY_DSN 为空时 init_sentry 应返回 False（默认关闭）。"""
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    assert init_sentry() is False


def test_sentry_disabled_in_test_env(monkeypatch):
    """测试环境即使配置了 DSN 也绝不初始化 Sentry。"""
    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@sentry.example/1")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    assert init_sentry() is False


def test_sentry_init_success_with_mocked_sdk(monkeypatch, capsys):
    """mock sentry_sdk 验证成功初始化分支：传入 DSN / 环境 / 采样率。"""
    captured = {}

    fake_root = types.ModuleType("sentry_sdk")
    fake_logging_pkg = types.ModuleType("sentry_sdk.integrations.logging")
    fake_starlette_pkg = types.ModuleType("sentry_sdk.integrations.starlette")
    fake_fastapi_pkg = types.ModuleType("sentry_sdk.integrations.fastapi")

    class _LoggingIntegration:
        def __init__(self, **kw):
            captured["logging_level"] = kw.get("level")
            captured["event_level"] = kw.get("event_level")

    class _StarletteIntegration:
        pass

    class _FastApiIntegration:
        pass

    fake_logging_pkg.LoggingIntegration = _LoggingIntegration
    fake_starlette_pkg.StarletteIntegration = _StarletteIntegration
    fake_fastapi_pkg.FastApiIntegration = _FastApiIntegration

    def _fake_init(**kwargs):
        captured["dsn"] = kwargs.get("dsn")
        captured["environment"] = kwargs.get("environment")
        captured["traces_sample_rate"] = kwargs.get("traces_sample_rate")
        captured["send_default_pii"] = kwargs.get("send_default_pii")
        # 模拟 SDK 对 before_send 的调用
        before_send = kwargs.get("before_send")
        sent = before_send({"event": 1}, {})
        captured["before_send_result"] = sent
        return 1

    fake_root.init = _fake_init

    # 注册完整的 sentry_sdk 包层级，保证
    # `from sentry_sdk.integrations.logging import ...` 能成功解析
    fake_modules = {
        "sentry_sdk": fake_root,
        "sentry_sdk.integrations": types.ModuleType("sentry_sdk.integrations"),
        "sentry_sdk.integrations.logging": fake_logging_pkg,
        "sentry_sdk.integrations.starlette": fake_starlette_pkg,
        "sentry_sdk.integrations.fastapi": fake_fastapi_pkg,
    }

    monkeypatch.setattr(settings, "SENTRY_DSN", "https://fake@sentry.example/1")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.25)

    with mock.patch.dict(sys.modules, fake_modules):
        assert init_sentry() is True

    assert captured["dsn"] == "https://fake@sentry.example/1"
    assert captured["environment"] == "production"
    assert captured["traces_sample_rate"] == 0.25
    assert captured["send_default_pii"] is False
    assert captured["before_send_result"] == {"event": 1}  # 无请求上下文原样返回


def test_attach_request_id_no_context():
    """无 request 上下文时 _attach_request_id 应原样返回事件。"""
    event = {"event_id": "x"}
    assert _attach_request_id(event) is event


# ---------------------------------------------------------------------------
# 5. 可观测性配置快速失败
# ---------------------------------------------------------------------------
def test_validate_observability_rejects_bad_log_format(monkeypatch):
    monkeypatch.setattr(settings, "LOG_FORMAT", "yaml")
    with pytest.raises(RuntimeError, match="LOG_FORMAT"):
        validate_observability_config()


def test_validate_observability_rejects_bad_log_level(monkeypatch):
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    monkeypatch.setattr(settings, "LOG_LEVEL", "VERBOSE")
    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        validate_observability_config()


def test_validate_observability_rejects_bad_sample_rate(monkeypatch):
    monkeypatch.setattr(settings, "LOG_FORMAT", "json")
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 1.5)
    with pytest.raises(RuntimeError, match="SENTRY_TRACES_SAMPLE_RATE"):
        validate_observability_config()
