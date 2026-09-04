# main 分支保护说明

> 本文件描述 WishinDiary 仓库的 `main` / `master` 分支保护规划。
> GitHub 分支保护规则需要在仓库 Settings → Branches 中人工启用（免费版即可创建"以规则集"或"经典分支保护规则"）。
> 下面的配置同时给出 Web 界面操作路径与 `gh` CLI 一键命令，二选一即可。

## 建议启用的保护规则

| 规则 | 建议值 | 说明 |
| --- | --- | --- |
| 合并前要求通过 Pull Request | 开启 | 禁止直接 push 到 main |
| 要求至少 1 名审阅人 | 开启（approved 1 人） | 个人开源项目单人维护可设为 1 人 |
| 合并前检查不通过时拒绝合并 | 开启 | 智能忽略 PR/提交时禁止合并 |
| 被阻止的强制推送 | 开启（Force push = 拒绝） | 防止历史被改写 |
| 被阻止的删除 | 开启 | 防止 main 分支被删 |
| 要求线性历史（rebase merge） | 建议开启 | 便于 `git bisect` 与 changelog |

## 必须通过的 CI 状态检查（Required status checks）

在 `main` 分支保护规则中，将以下 status check 设为 required：

- `Backend Test Suite`（含 pytest 覆盖率门槛 80%）
- `Frontend Build Check`（含 vue-tsc 类型检查、Vitest、ESLint、Prettier）
- `Analyze (python)`（CodeQL）
- `Analyze (javascript-typescript)`（CodeQL）

> 说明：`security-scan`（Trivy）与 `frontend-e2e`（Playwright）建议也设为
> required；若 E2E 偶发不稳定，可先在 required 列表外观察一周再纳入。

`gh` CLI 一键创建"经典分支保护规则"示例：

```bash
gh api -X PUT repos/{owner}/{repo}/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks[][context]="Backend Test Suite" \
  -f required_status_checks[][context]="Frontend Build Check" \
  -f required_status_checks[][context]="Analyze (python)" \
  -f required_status_checks[][context]="Analyze (javascript-typescript)" \
  -f required_status_checks[strict]=true \
  -f enforce_admins=true \
  -f required_pull_request_reviews[required_approving_review_count]=1 \
  -f required_pull_request_reviews[dismiss_stale_reviews]=true \
  -f restrictions=null
```

## 更新规则（维护流程）

- 每次在 `.github/workflows/` 下新增 job 并希望它作为合并门槛时，
  同步在 Settings 中把它加入 required status checks，并更新本文件。
- 分支保护属于仓库级配置，无法通过 PR 直接生效（仅能通过本说明文件留档）。

## 关联发布流程

- 只有经过保护检查的 `main` 才允许打 `v*` 标签；标签触发
  `.github/workflows/release.yml`（见 `docs/DEPENDENCY_PINNING.md` 与 Release 工作流）。
- 发布前请按 `docs/RELEASE_CHECKLIST.md` 核对数据库迁移、模型哈希与 CHANGELOG。
