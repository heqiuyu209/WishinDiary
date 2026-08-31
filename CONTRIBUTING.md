# Contributing to WishinDiary

感谢参与。请先阅读 `SECURITY.md`，不要在 issue 或 pull request 中粘贴密码、JWT、真实健康数据、数据库转储或私有模型。

## 开发流程

1. Fork 仓库并创建功能分支。
2. 使用 Python 3.12 和 Node.js 22.18 或更高版本。
3. 后端安装 `wishindiary-api/requirements-dev.txt`，前端执行 `npm ci`。
4. 只使用合成数据编写测试和演示。
5. 修改 API 时同步更新测试和 README。

## 提交前检查

```bash
cd wishindiary-api
python -m pytest
python -m ruff check app scripts tests

cd ../Wishindiary-web
npm run build
npm audit --audit-level=high
```

## 模型变更

模型只能使用授权数据或纯合成数据。模型文件必须是 `.skops`，并更新 `MODEL_CARD.md`、依赖版本、SHA-256 和评估指标。禁止提交 pickle/joblib 模型。

## Commit 与 PR

- Commit 使用清晰的动词开头，例如 `Fix cycle date validation`。
- PR 描述包含动机、行为变化、测试结果和必要的截图。
- 不要把重构、依赖升级和无关格式化混在一个 PR 中。
