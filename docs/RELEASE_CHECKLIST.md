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

模型不随发行版发布：`*.skops` 已在 .gitignore 排除，一律由 `scripts/train.py`
本地生成（见 MODEL_CARD.md），发布内容不包含模型文件。

## GitHub 仓库设置

首次推送后建议启用：

- Settings → Security → Private vulnerability reporting
- Dependabot alerts 与 Dependabot security updates
- Secret scanning 与 push protection（仓库套餐支持时）
- `main` 分支保护：要求 CI 通过、禁止 force push
- Issues/PR 模板和明确的维护者联系方式

发布 Release 前给版本打签名标签，并在说明中记录数据库迁移、模型哈希和兼容范围。

## 首个正式版本 v1.0.0 发布流程（与 release.yml 打通）

`.github/workflows/release.yml` 会在推送 `v*` 标签时自动校验后端测试与前端构建、生成 Changelog、扫描 SBOM 并把以下资产挂到 Release：SBOM、数据库迁移（`migrations/versions/*.py`）、`requirements.txt` 与 `MODEL_CARD.md`（模型不随发行版附送，见 MODEL_CARD.md）。发布 v1.0.0 的步骤如下：

1. **冻结范围**：确认 CHANGELOG 的 `[Unreleased]` 已整理，合并所有计划进入 v1.0.0 的 PR。
2. **核对迁移与模型**
   - 运行 `cd wishindiary-api && python -m alembic heads`，确认只有一个 head，并把 head 编号记录进 Release 说明。
   - 运行 `python scripts/inspect_model.py`，确认本地生成模型的 `MODEL_SHA256` 与 `MODEL_CARD.md` 记录的评估基准哈希一致（模型不随发行版附送）。
3. **更新 CHANGELOG**：新建 `[1.0.0] - <日期>` 小节，将 Unreleased 内容移入并补充"升级说明"段（见下方模板）。
4. **运行全部自动检查**（见本文档开头），确保后端测试、Ruff、前端构建、npm audit 与 `docker compose config` 全部通过。
5. **打标签并推送**：
   ```bash
   git add -A
   git commit -m "Release v1.0.0"
   git tag -s v1.0.0 -m "WishinDiary v1.0.0"
   git push origin main
   git push origin v1.0.0
   ```
   推送标签会触发 `release.yml`；请到 GitHub Release 页面用下方"Release 说明模板"复核或补写正文后再正式发布。

## Release 说明模板（数据库迁移 / 模型评估基准 / 兼容范围）

每个正式 Release 的说明正文应包含以下内容，其中号部分每次发布时替换：

> ## WishinDiary vX.Y.Z (YYYY-MM-DD)
>
> ### 变更摘要
> - （简要列出主要新增与修复，可引用 CHANGELOG）
>
> ### 数据库迁移
> - Alembic head：`<head 版本号，例如 0002_add_refresh_tokens>`
> - 升级命令：`python -m alembic upgrade head`（本地）或重建容器（Docker Compose）
> - 回滚：`python -m alembic downgrade -1`（如需回滚到上一版本）
>
> ### 模型
> - 模型：不随发行版附送，由 `scripts/train.py --synthetic-only` 本地生成（见 MODEL_CARD.md）。
> - 本地评估基准：`cycle-rf-v2`，SHA-256 见 MODEL_CARD.md（当前 `bd315ff749b13f37ba601f68c1e1a56a77c1dd507aa88e9d498fb052220ed3eb`）。
> - 兼容性：按 `wishindiary-api/requirements.txt` 锁定的 scikit-learn 版本生成模型，避免运行时不匹配。
>
> ### 兼容范围
> - 兼容的 API 版本：`/api/v1`；本版本内尚未出现破坏性变更，若有请在此列出。
> - 支持环境：Python 3.12、Node.js 22.18+、MySQL 8.0+、Docker Compose。
> - 数据兼容：依赖数据库迁移，升级前请先备份（`scripts/backup_database.sh`）。

> 注意：本地生成模型后请用 `scripts/inspect_model.py` 校正 `MODEL_SHA256`（Docker 部署由 `setup_docker.ps1` 自动写入）；校验值用于与 `MODEL_CARD.md` 评估基准比对，避免误用旧模型。

## 发布版本规划

- **v1.0.0（首个正式版）**：以当前"当前基线 + P0 安全 + P1 代码结构 + 可观测性"完成范围作为 1.0 冻结范围，作为公开使用的稳定基线。
- **v1.x.y（后续）**：按语义化版本继续推进 P1 前端工程化、测试/CI 增强、机器学习质量等未完成项。
- **v2.0.0（未来的破坏性变更）**：如引入 API 破坏性变更（如 v2 接口）、数据库不兼容迁移或模型格式变更，需提升主版本号并在 Release 中显著声明。
