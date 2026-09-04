## 概述

用一两句话说明本次变更的动机和目标。关联的 issue 编号（如有）。

## 变更内容

- 后端 / 前端 / 文档 / 部署（选择划分）
- 具体改动点列表

## 是否涉及迁移

- [ ] 是，已新增 Alembic 迁移（迁移文件位于 `wishindiary-api/migrations/versions/`），并确认 `alembic heads` 只有一个 head
- [ ] 否

## 是否涉及模型

- [ ] 是，已按 CONTRIBUTING.md 更新 `MODEL_CARD.md`（版本、SHA-256、依赖、评估指标），模型文件为 `.skops`
- [ ] 否

## 测试

列出本地验证结果：

```bash
cd wishindiary-api
python -m pytest
python -m ruff check app scripts tests

cd ../Wishindiary-web
npm run build
npm audit --audit-level=high
```

- 后端测试通过：是 / 否（附通过数量）
- Ruff 通过：是 / 否
- 前端构建通过：是 / 否
- npm audit 通过：是 / 否

## 行为变化

本次变更对外部可见的行为或 API 是否有变化？如有，请说明并更新相关文档。

## 截图（可选）

UI 变更请附截图。

## 安全检查

- [ ] 我确认 PR 中不含 `.env`、密码、JWT 密钥、数据库口令、真实健康数据、数据库转储或私有模型文件
- [ ] 我把重构、依赖升级和无关格式化拆分到了独立提交 / PR
