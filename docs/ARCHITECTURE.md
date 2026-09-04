# WishinDiary 后端架构说明（ARCHITECTURE）

> 版本：v1 · 对应代码：`wishindiary-api/app`（FastAPI + MySQL + Vue3 前端）
> 本文描述当前分层架构、目录结构、请求数据流、事务与错误处理约定，供新开发者快速理解代码组织方式。

## 1. 架构总览

WishinDiary 后端采用**四层分层架构**：

```
HTTP 请求
   │
   ▼
┌────────────────────────────┐
│  Router 层（app/routers）   │  薄路由：请求解析 / 鉴权 / 响应返回，不含业务与 DB
├────────────────────────────┤
│  Schema 层（app/schemas）   │  Pydantic 请求/响应模型，统一 API 类型契约
├────────────────────────────┤
│  Service 层（app/services） │  业务规则 / 事务编排 / 调用 Repository，抛 AppError
├────────────────────────────┤
│  Repository 层（app/repositories）│  纯数据访问函数（cursor, ...），SQL 唯一入口
│                            │  底部：MySQL（通过 app.core.database 连接池）
└────────────────────────────┘
```

依赖方向**自上而下单向**：Router → Service → Repository，禁止反向依赖或越层调用（Router 不得直连 DB）。

## 2. 目录结构

```
wishindiary-api/
├── app/
│   ├── main.py                  # FastAPI 实例、中间件、路由注册、统一异常处理器挂载
│   ├── core/                    # 横切关注点
│   │   ├── config.py            # 配置（pydantic-settings）
│   │   ├── database.py          # 连接池 + transaction() 事务上下文
│   │   ├── errors.py            # AppError + 统一异常处理器
│   │   ├── csrf.py              # Cookie 认证的 CSRF 纵深防御中间件
│   │   └── audit.py             # 登录/数据修改/敏感操作审计日志
│   ├── schemas/                 # Pydantic 请求/响应模型（统一 API 类型）
│   │   ├── common.py            # ErrorResponse / ErrorDetail / StatusResponse
│   │   ├── auth.py  cycle.py  daily_log.py
│   │   ├── prediction.py  report.py  stats.py  user_data.py
│   ├── repositories/            # 数据访问层（函数式，签名 (cursor, ...)）
│   │   ├── cycle_repository.py  daily_log_repository.py
│   │   ├── prediction_log_repository.py
│   │   ├── report_repository.py  stats_repository.py
│   ├── services/                # 业务层（类式，面向业务能力）
│   │   ├── cycle_service.py     # 周期写入（log_start/log_end/update/delete）
│   │   ├── daily_log_service.py # 每日健康日志
│   │   ├── prediction_service.py# 预测：特征提取→推理→监控→待对账写入
│   │   ├── stats_service.py  report_service.py  user_data_service.py
│   │   └── cycle_prediction_service.py  # 离线模型推理封装
│   ├── features/                # 特征工程（周期/健康特征提取）
│   ├── ml/                      # 模型契约、校验、监控、离线训练产物
│   └── routers/                 # HTTP 层（全部业务接口挂 /api/v1 前缀）
│       ├── auth.py  cycles.py  daily_logs.py  prediction.py
│       ├── stats.py  report.py  user_data.py
├── tests/                       # pytest（Alembic 建测试库）
├── migrations/                  # Alembic 迁移（0001_initial_schema.py 等）
└── ml/                          # 预训练模型 .skops / 训练脚本
```

## 3. 各层职责与约定

### 3.1 Router 层（`app/routers/`）

- 只做：声明 HTTP 端点、解析请求（依赖注入、Pydantic 模型）、调用 Service、返回响应。
- 不包含：SQL、业务规则、事务管理。
- 所有业务路由使用 `prefix="/api/v1"`（auth 为 `/api/v1/auth`），见 ADR-002。
- 鉴权依赖 `get_current_user_id`（从 `app.routers.auth` 导入）注入 `user_id`。

### 3.2 Schema 层（`app/schemas/`）

- 请求/响应均为 Pydantic 模型，禁止裸 dict 返回（见 ADR-002 与 P1-7）。
- 统一错误结构定义于 `common.py`：

```json
{"error": {"code": "not_found", "message": "周期不存在", "detail": null}}
```

### 3.3 Service 层（`app/services/`）

- 承载业务规则与用例编排，是**唯一允许管理事务**的层。
- 通过 `with transaction() as connection:` 获得连接并自动 commit/rollback（见 §4）。
- 可预期失败抛出 `AppError(status_code, code, message, detail)`；未预期异常由全局处理器兜底转 500。
- 复杂业务规则（周期计算、特征提取、预测、数据导出级联删除）在本层实现，并配套 service 层单元测试（`tests/test_services.py`）。

### 3.4 Repository 层（`app/repositories/`）

- 纯数据访问：函数接收 `cursor`，返回行 dict / 列表，SQL 全部集中于此。
- 不处理业务逻辑，不做事务提交/回滚（由调用方 Service 通过 `transaction()` 管理）。
- 通过 `app/repositories/__init__.py` 统一导出，Service 只依赖导出的函数名。

## 4. 统一事务管理

`app/core/database.py` 提供唯一事务入口：

```python
with transaction() as connection:      # 成功自动 commit，异常自动 rollback 并重新抛出
    with connection.cursor() as cursor:
        repo_func(cursor, ...)
```

约定：

- **谁管理事务：Service 层。** Router 不持有连接；Repository 不提交。
- 同一用例内的多步写操作必须包在同一个 `transaction()` 内，保证原子性（例如 `update_cycle` 中更新日期 + 重算周期长度）。
- 业务失败通过抛 `AppError` 表达；`transaction()` 捕获任意异常回滚，随后全局异常处理器收敛为统一错误响应。

## 5. 统一异常与错误响应

`app/core/errors.py` 定义：

- `AppError(status_code, code, message, detail)`：业务层可预期失败。
- `register_exception_handlers(app)`：在 `main.py` 中挂载，收敛以下异常为统一 `{"error": {...}}` 结构：
  - `AppError` → 原样映射；
  - `starlette HTTPException` → 按状态码映射错误码（400→invalid_input、401→unauthorized、404→not_found、429→rate_limited、500→internal_error 等）；
  - Pydantic 校验错误 → 422 `validation_error`；
  - 未预期异常 → 500 `internal_error`（并记录日志）。

前端按 `err.response?.data?.error?.message` 解析错误（见 `Wishindiary-web/src/api/httpClient.js` 与各视图）。

## 6. 请求数据流示例：周期写入

以 `POST /api/v1/cycles/start` 为例：

1. `app/routers/cycles.py` 解析 `LogStartRequest`，注入 `user_id`；
2. 调用 `CycleService().log_start(user_id, start_date)`；
3. `CycleService` 进入 `transaction()`，调用 `cycle_repository` 查询/写入；
4. Repository 只执行 SQL；
5. 成功 → 返回 Pydantic `CycleOperationResponse`；失败 → 抛 `AppError`；
6. 全局异常处理器（若失败）收敛为 `{"error": {...}}`。

## 7. API 版本与健康检查

- 业务接口统一挂 `/api/v1` 前缀（auth/cycles/daily_logs/prediction/stats/report/user_data）。
- `/api/health` 保留为无版本前缀的探活端点（不做 DB 强依赖语义）。
- 前端 `VITE_API_BASE_URL=http://localhost:8000`，请求路径形如 `/api/v1/auth/login`、`/api/v1/cycles/list`。

## 8. 数据库迁移

- 数据库结构统一由 Alembic 管理（`wishindiary-api/migrations/`），`schema.sql` 已废弃。
- 测试库 `wishindiary_test_db` 同样由 Alembic 建表（见 `tests/conftest.py`），避免结构与生产漂移（见 ADR-003）。

## 9. 测试

- `pytest`（`wishindiary-api/tests/`）：API 集成测试 + service 层单元测试。
- `tests/test_services.py` 通过 monkeypatch 替换 `transaction()` 与 repository 函数，离线验证业务规则。
- 统一错误格式变更后，测试断言同步使用 `res.json()["error"]["message"]`。

## 10. 架构决策记录

重要架构决策见 `docs/adr/`：
- ADR-001：分层架构（router/schema/service/repository）
- ADR-002：API 版本化 `/api/v1`
- ADR-003：Alembic 数据库迁移选型
