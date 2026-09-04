# Changelog

本项目使用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范，版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)（SemVer）。

格式：`vMAJOR.MINOR.PATCH`，例如 `v1.0.0`；预发布为 `vMAJOR.MINOR.PATCH-rc.N`。每次正式发布时，请把 [Unreleased] 下的变更移动到新版本小节，并更新仓库 `v*` 标签。

## [Unreleased]

### 新增

- 增加贡献者公约（Contributor Covenant 2.1）与维护者联系方式。
- 增加 Issue 模板（Bug / 功能建议 / 使用咨询）与 Pull Request 模板，规范 issue 提交与 PR 描述。
- 增加本 CHANGELOG，并规划首个正式版本 v1.0.0 的发布流程与 Release 说明模板。

## [0.9.0] - 2026-09-02

首个可发布里程碑的整合版本（尚未作为正式 Release 发布，用于标注当前完成范围）。

### 新增（当前基线）

- 前后端基础功能可运行：FastAPI + MySQL + Vue 3。
- Docker Compose 本地一键部署（MySQL + API + Nginx Web），默认只绑定本机地址。
- JWT 登录与登出，凭据通过 HttpOnly Cookie 传递，不写入登录响应体。
- 用户数据查询按 `user_id` 隔离，多用户数据互不可见。
- 周期记录、趋势看板、结构健康报告与本地随机森林预测。
- 模型以 `.skops` 交付，附带 SHA-256 与特征契约校验；提供 `MODEL_CARD.md`。
- README、贡献指南（CONTRIBUTING）、安全策略（SECURITY）等内容文档。
- 纯合成数据训练脚本，训练不读取真实用户数据库。

### P0：安全与数据可靠性

- 引入 Alembic 数据库迁移，建立统一的 schema 版本记录与回滚策略，不再维护 `schema.sql`。
- 登录接口限流升级为可共享的限流方案（不再依赖进程内字典）。
- 明确并实现基于 HttpOnly Cookie 的 CSRF 防护策略。
- 设计并实现 Token 过期、刷新、撤销与退出登录策略，新增 `refresh_tokens` 迁移。
- 增加登录、数据修改和敏感操作的审计日志。
- 补充用户 A/B 数据隔离、越权修改与越权删除测试。
- 设计健康数据的导出（数据可携带）、删除（级联清理）、保留期限与备份恢复策略。

### P1：代码结构和可维护性

- 拆分 `app/routers/cycles.py`，按 router、schema、service、repository 分层。
- 统一事务管理、异常处理与 API 错误响应格式。
- 引入 `/api/v1` API 版本前缀并统一请求/响应类型定义。
- 增加架构说明文档（`docs/ARCHITECTURE.md`）与架构决策记录（ADR-001/002/003）。
- 为复杂业务规则补充 service 层单元测试。

### P1：可观测性与部署

- 增加 request ID 便于全链路追踪。
- 日志改为结构化输出，增加请求耗时、错误率、数据库连接池与模型推理指标。
- 支持接入 Sentry 并输出 OpenTelemetry 相关数据。
- 设计并实现生产环境 TLS 终止方案（Nginx/Caddy 终止 TLS，`/api/` 反代到 API）。
- 提供自动化数据库备份与恢复演练文档与脚本。

## [0.1.0] - 开发早期

- 项目初始化，建立 FastAPI 后端与 Vue 3 前端骨架。
- 验证本地与 Docker Compose 两种运行方式的可行性。

[Unreleased]: https://github.com/heqiuyu209/WishinDiary/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/heqiuyu209/WishinDiary/compare/v0.1.0...v0.9.0
[0.1.0]: https://github.com/heqiuyu209/WishinDiary/releases/tag/v0.1.0
