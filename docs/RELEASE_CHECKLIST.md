# GitHub 发布前检查

## 自动检查

在 PowerShell 中从仓库根目录运行：

```powershell
cd C:\path\to\WishinDiary\wishindiary-api
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check app scripts tests
..\.venv\Scripts\python.exe scripts\inspect_model.py

cd ..\Wishindiary-web
npm ci
npm run build
npm audit --audit-level=high --registry=https://registry.npmjs.org

cd ..
docker compose config
```

## 提交内容检查

初始化 Git 并暂存后运行：

```powershell
git diff --cached --check
git status --short
git ls-files | Select-String -Pattern '(^|/)(\.env|node_modules|\.venv|\.idea|\.claude)(/|$)|\.(pkl|pickle|joblib|db|sqlite3?)$'
```

最后一条命令应没有输出。人工确认暂存区不包含：

- `.env`、数据库口令、JWT 密钥、访问令牌
- 数据库文件、SQL 转储、真实用户健康数据、日志
- `node_modules`、虚拟环境、IDE 配置、缓存、前端 `dist`
- pickle/joblib 模型或未经授权的数据集、模型权重
- 个人绝对路径、内网地址、私有下载链接

只允许发布经过审计并记录哈希的
`wishindiary-api/ml/menstrual_rf_model.skops`。

## GitHub 仓库设置

首次推送后建议启用：

- Settings → Security → Private vulnerability reporting
- Dependabot alerts 与 Dependabot security updates
- Secret scanning 与 push protection（仓库套餐支持时）
- `main` 分支保护：要求 CI 通过、禁止 force push
- Issues/PR 模板和明确的维护者联系方式

发布 Release 前给版本打签名标签，并在说明中记录数据库迁移、模型哈希和兼容范围。
