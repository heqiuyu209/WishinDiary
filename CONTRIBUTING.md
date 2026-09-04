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

模型只能使用授权数据或纯合成数据。仓库**不附带预训练模型文件**（`*.skops` 不入库）；若需随改动提交评估基准，文件必须是 `.skops`，并同步更新 `MODEL_CARD.md`、依赖版本、SHA-256 和评估指标。禁止提交 pickle/joblib 模型。

## Commit 与 PR

- Commit 使用清晰的动词开头，例如 `Fix cycle date validation`。
- PR 描述包含动机、行为变化、测试结果和必要的截图。
- 不要把重构、依赖升级和无关格式化混在一个 PR 中。

## 维护者（Maintainers）与问题响应范围

> 说明：维护者联系渠道见下；响应时限为当前单人维护的承诺值，会随维护规模调整。

- **项目维护者**：`heqiuyu209`
- **邮箱**：`2097187372@qq.com`
- **GitHub**：[heqiuyu209/WishinDiary](https://github.com/heqiuyu209/WishinDiary)
- **首选渠道**：GitHub issue（优先）、邮件（敏感问题）。

### 问题响应范围

- **会响应**：Bug 复现与修复、安全问题（走 SECURITY.md 私有渠道）、文档纠正、部署与配置使用问题、周期预测相关的模型质量问题。
- **响应时限**：常规 issue 72 小时内首次回复，安全漏洞 24 小时内回应；节假日可能顺延。
- **不在范围内（请自行排查）**：非本仓库代码导致的第三方依赖安装问题、未按 README 要求环境（Python/Node/MySQL 版本不符）的兼容问题、对模型结果作医疗解读——本项目明确不做诊断、治疗、避孕或紧急医疗判断。
- **模型变更**：任何影响发布模型的行为必须遵守 [MODEL_CARD.md](MODEL_CARD.md) 的安全发布要求，并同步更新模型卡与哈希。

### 维护其它说明

- 维护者为单人/小团队，回复可能有延迟，请理解。
- 所有交互均应遵循 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。不当行为可通过维护者邮箱举报。
