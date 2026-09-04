# ADR-003：采用 Alembic 管理数据库迁移

- 状态：已接受（2026-09-02）
- 涉及：P0 安全和数据可靠性 / P1 代码结构与可维护性（迁移选型）

## 背景

此前数据库结构维护存在多处重复：`schema.sql` 与 `tests/conftest.py` 分别维护同一结构，开发期结构变更易导致两者漂移；缺乏版本记录与回滚策略。

## 决策

- 引入 **Alembic** 作为唯一数据库迁移工具（选型理由见下）。
- 迁移文件位于 `wishindiary-api/migrations/`，初始迁移 `0001_initial_schema.py` 建立四张业务表 + `login_attempts` 表。
- 测试库 `wishindiary_test_db` 由 Alembic 建表（`tests/conftest.py` 调用迁移），与生产结构单一来源一致。
- 废弃 `schema.sql`。

## 选型对比

| 工具 | 结论 |
|---|---|
| Alembic | 采用。与 SQLAlchemy/FastAPI 生态契合，Python 原生、可编程回滚、社区成熟 |
| Flyway | 不采用。Java 生态工具，对纯 Python 项目集成成本高 |
| Liquibase | 不采用。XML/YAML 描述式，较笨重且引入额外概念 |

## 后果

- 正向：结构变更可追溯、可回滚；测试库与生产库结构一致；后续迁移有版本链。
- 反向：开发者需学习 Alembic 命令（`revision --autogenerate` / `upgrade` / `downgrade`）；autogenerate 生成的迁移需人工复核。
- 约定：生产环境部署须先执行 `alembic upgrade head` 再启动 API（见 `docs/DEPLOYMENT.md`）。
