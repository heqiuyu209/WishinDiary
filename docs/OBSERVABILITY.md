# WishinDiary 可观测性设计与运维指南

> 覆盖与可观测性相关的实现：request ID、结构化日志、
> API/DB/模型的指标采集、Sentry 接入，以及生产配置校验与部署前检查。
> 部署与 TLS 见 docs/DEPLOYMENT.md、docs/TLS_TERMINATION.md；备份恢复见 docs/BACKUP_DR.md。

## 1. 总览

| 关注维度 | 实现位置 | 输出 |
| --- | --- | --- |
| 链路标识 | `app/core/request_id.py`（RequestIDMiddleware） | `X-Request-ID` 请求/响应头 + 日志字段 |
| 结构化日志 | `app/core/logging_config.py` | 单行 JSON（生产）或可读文本（开发） |
| API 耗时/错误率 | `app/core/metrics.py`（MetricsMiddleware） | `wishindiary.access` 日志 + `/metrics` |
| 数据库连接池 | `app/core/metrics.py` `_pool_snapshot()` | 访问日志 `pool` 字段 + `/metrics` gauge |
| 模型推理 | `app/services/prediction_service.py` 调用 `record_model_inference()` | `wishindiary.model` 日志 + `/metrics` |
| 错误上报 | `app/core/sentry_client.py` | Sentry（DSN 非空才启用，env 可开关） |
| 指标导出 | `app/main.py`（`METRICS_ENABLED=true` 时挂 `/metrics`） | Prometheus 文本格式 |

## 2. request ID

- 每个请求生成唯一 `request_id`（UUID4 hex）；若上游（Nginx / 网关）已带
  `X-Request-ID` 则**透传**，便于跨跳转串联。
- 通过 `contextvars` 注入当前异步上下文，中间件期间产生的所有日志自动携带。
- 响应头统一回传 `X-Request-ID`，前端/CLI 可据此对照日志排查。

```bash
curl -i http://127.0.0.1:8000/api/health | grep -i x-request-id
```

## 3. 结构化日志

`setup_logging()` 在应用启动时配置统一 handler；`LOG_FORMAT=json`（生产默认）输出
单行 JSON，`LOG_FORMAT=text` 供本地开发可读。`LOG_LEVEL` 控制级别。

统一字段（JSON 格式示例）：

```json
{"ts": "2026-09-02T12:00:00.000Z", "logger": "wishindiary.access", "level": "INFO",
 "message": "http_request", "request_id": "3f2a...", "method": "GET",
 "path": "/api/v1/cycles/:id", "status": 200, "duration_ms": 12.345,
 "pool": {"max_connections": 5, "idle_connections": 2, "in_use_connections": 1}}
```

- 关键路径（访问日志、模型推理、审计、错误异常）均以 logger 名区分：
  `wishindiary.access` / `wishindiary.model` / `wishindiary` / `uvicorn`。
- 敏感信息不落日志：密码、JWT、Cookie、日记正文均不输出（SECURITY/审计规范见
  docs/DATA_LIFECYCLE.md）。

## 4. 指标（日志侧 + Prometheus 双通道）

### 4.1 结构化日志指标（始终启用，推荐默认采集）

- **API 耗时/错误率**：每条请求结束输出 `wishindiary.access`（见上），含
  `duration_ms` 与 `status`，用 Loki/Elastic 聚合 `status>=500` 即得错误率。
- **数据库连接池**：访问日志附带 `pool` 字段（`max/created/idle/in_use_connections`），
  连接池耗尽时可定位 DB 瓶颈。
- **模型推理**：每次预测输出 `wishindiary.model`（metric=model_inference），含
  `model_version`、`latency_ms`、`success`、`user_id`（脱敏可在采集端处理）。

### 4.2 Prometheus 文本格式（可选）

`.env` 设 `METRICS_ENABLED=true` 后，`GET /metrics` 返回 Prometheus 文本格式。
路径已做基数归一化（`/api/v1/cycles/123` → `/api/v1/cycles/:id`）。

```bash
curl http://127.0.0.1:8000/metrics | grep wishindiary_
```

指标清单：

| 指标名 | 类型 | 含义 |
| --- | --- | --- |
| `wishindiary_http_requests_total` | counter | 请求总数（method+path） |
| `wishindiary_http_errors_total` | counter | 5xx 错误数 |
| `wishindiary_http_duration_ms_total` | counter | 请求总耗时（毫秒） |
| `wishindiary_db_pool_max_connections` | gauge | 连接池上限 |
| `wishindiary_db_pool_created_connections` | gauge | 已创建连接数 |
| `wishindiary_db_pool_idle_connections` | gauge | 空闲连接数 |
| `wishindiary_db_pool_in_use_connections` | gauge | 使用中连接数 |
| `wishindiary_model_inference_total` | counter | 推理总次数（model_version） |
| `wishindiary_model_inference_errors_total` | counter | 推理失败数 |
| `wishindiary_model_inference_duration_ms_total` | counter | 推理总耗时 |

Grafana 告警示例口径：错误率 = `sum(rate(errors_total[5m])) / sum(rate(requests_total[5m]))`；
连接池饱和 = `pool_in_use_connections >= pool_max_connections` 持续 5 分钟。

> 指标为**进程内计数**，多副本部署时建议聚合后使用，或后续接入 OTel/Prometheus
> 客户端库（见 §8）。

## 5. Sentry（错误上报）

- `.env` 配置 `SENTRY_DSN` 即启用；留空完全禁用（env 可开关）。
- 测试环境（`ENVIRONMENT=test`）**永不初始化**，不影响单测。
- 自动上报未处理异常；`SENTRY_TRACES_SAMPLE_RATE` 控制性能采样。
- 日志中的 `request_id` 会写入 Sentry event tags，面板上可按 `request_id` 检索。
- 关闭 PII 上报（`send_default_pii=False`），保护健康数据。

```dotenv
SENTRY_DSN=https://<key>@sentry.example.com/1
SENTRY_TRACES_SAMPLE_RATE=0.1
```

## 6. 生产配置校验与部署前检查（Fail fast）

- **启动时**：`app/core/config.py` 在 settings 加载后执行
  `validate_security_baseline()` 与 `validate_observability_config()`，关键环境变量
  缺失/非法（如 `SECRET_KEY` 过短、`LOG_FORMAT` 非法、采样率越界）立即抛
  `RuntimeError`，进程快速失败，杜绝带病启动。
- **部署前**：运行 `scripts/check_production.py` 静态检查 `.env`/环境变量、
  模型文件哈希、CORS 通配符等，返回非零退出码表示存在 FAIL 项：

```bash
cd wishindiary-api
python scripts/check_production.py            # 默认读项目根 .env
python scripts/check_production.py --env .env.production
```

- **Compose 配置校验**：`docker compose config`（发布前检查清单见
  docs/RELEASE_CHECKLIST.md）。

## 7. 运维查询示例

```bash
# 查看最近请求日志（Loki/ELK 侧按字段过滤）
journalctl -u wishindiary-api -n 200 --no-pager | grep '"logger":"wishindiary.access"'

# 按 request_id 定位单次请求全链路
grep '"request_id":"<request_id>"' /var/log/wishindiary/api.log

# 查看模型推理指标
curl -s http://127.0.0.1:8000/metrics | grep model_inference
```

## 8. 选型说明与演进

- 选用「结构化日志指标 + 可选 /metrics 文本端点」而非引入完整 Prometheus 客户端/
  OTel SDK，是为了在单机开源部署下保持零外部依赖、运维简单。
- 已预留演进路径：`metrics.py` 计数结构可无缝替换为
  `prometheus_client` / OpenTelemetry metrics SDK；Sentry 已基于官方 SDK 接入，
  如需全链路追踪可追加 `opentelemetry-instrumentation-fastapi`。
