# ADR-001：后端四层分层架构

- 状态：已接受（2026-09-02）
- 涉及：P1 代码结构与可维护性

## 背景

`app/routers/cycles.py` 曾为约 492 行的单体文件，同时承担 HTTP 契约、周期业务规则（周期计算、特征提取、prediction_logs 对账）与 SQL 访问。stats/report/user_data 路由同样直连 DB。问题：

- 业务规则无法脱离 DB 单独测试；
- 路由/业务/SQL 耦合，修改易引入回归；
- 同一份周期逻辑难以被多接口复用。

## 决策

将后端拆为四层单向依赖：

```
Router（HTTP 契约） → Schema（Pydantic 类型） → Service（业务+事务） → Repository（SQL）
```

- Router：仅解析请求、调用 Service、返回响应；
- Schema：统一请求/响应 Pydantic 模型；
- Service：业务规则与事务编排，抛出 `AppError`；
- Repository：函数式 `(cursor, ...)`，SQL 唯一入口。

`cycles.py` 拆为 `routers/cycles.py`（薄路由）、`schemas/cycle.py`、`services/cycle_service.py`、`repositories/cycle_repository.py`；每日日志、预测、统计、报告、数据导出均按同构分层。

## 后果

- 正向：业务规则可用 monkeypatch 的 service 层单元测试覆盖（`tests/test_services.py`）；依赖方向清晰；跨接口复用成为可能。
- 反向：分层增加样板代码；Service/Repository 命名与边界需在评审中保持一致。
- 权衡：跨层抛错统一通过 `AppError` 表达，避免层层吞异常。
