# GitHub Actions 与依赖固定（Pin）评估

> 目的：减少"供应链移动目标"风险——即 third-party Actions 与基础镜像
> 在未固定版本的情况下被替换/篡改，或依赖可视化升级引入回归。
> 本文档记录当前策略、落地状态与后续演进建议。

## 1. 现状与风险

- 现有 CI 使用 `actions/checkout@v4`、`actions/setup-python@v5` 等 **major 版本标签**。
  GitHub 只允许 major tag 可变（`v4` 的次要/补丁会被 actions 生态维护者移动更新），
  因此 major tag 是一个"有浮动的固定点"：安全上优于 `@main`/`@master`，但劣于完整 SHA。
- 镜像服务 `mysql:8.0`、前端/后端 Dockerfile 的基础镜像使用 major/minor tag，
  同样属于浮动点。

## 2. 落地策略（当前已按此执行）

**原则：major 版本标签 + Dependabot 自动跟踪更新 + 依赖锁文件三重防线。**

| 层级 | 当前做法 |
| --- | --- |
| GitHub Actions | 使用 major/minor 版本标签（`@v4` / `@v5` / `@v3` / `@v0.24.0`） |
| Actions 自动更新 | `.github/dependabot.yml` 已启用 `github-actions` 生态，每周扫描 |
| npm 依赖 | 前端 `package-lock.json` 已提交，Dependabot 每周更新 |
| Python 依赖 | 后端 `requirements.txt` / `requirements-dev.txt` 已固定版本号，Dependabot 每周更新 |
| SBOM | CI `security-scan` job 与 Release 工作流均生成 SPDX SBOM（Syft） |

## 3. 更高强度的 SHA pin（后续建议）

若项目进入多维护者阶段或发布正式对外版本，建议将 **Release 工作流** 中的
高风险 Actions 升级为完整 SHA digest：

```yaml
- uses: actions/checkout@b4de6a6a8c39f6e5930e8f8f8f8f8f8f8f8f8f8  # v4.x 的完整 SHA
```

实施步骤：

1. 在 GitHub → marketplace 每个 Action 版本页复制完整 commit SHA；
2. 替换 tag 引用，并在注释中标注对应的 tag 便于阅读；
3. 配合 Dependabot 的 `github-actions` 更新仍能自动升级（Dependabot 支持 SHA→tag→SHA 更新）；
4. 该策略变更以"每季度一次、每次一个 workflow"的节奏执行，避免频繁 churn。

> 为什么当前不全量 SHA？：个人开源项目维护成本 < 风险暴露（仓库无写权限的外部
> 提权攻击面小），且 major tag + Dependabot 已能阻止大多数供应链漂移；
> 一旦提权到组织级多协作者，立即切换到 SHA pin。

## 4. 基础镜像固定评估

- `docker-compose.yml` 的 `mysql:8.0` 与两个 Dockerfile 的基础镜像：
  - Docker 镜像的 `:8.0` / `:22` 等 minor 级 tag 会被镜像维护者定期推进，
    存在运行时行为漂移的可能。
  - 建议（发布期落地）：在 Dockerfile 与 docker-compose 中改用 **digest** 引用，
    并在每次升级后更新 .env 说明。示例：

    ```dockerfile
    FROM python:3.12-slim@sha256:<完整 digest>
    ```

- 本阶段不强制执行：由于本地 Docker 环境未统一（跨架构 digest 不同），
  立刻 pin digest 会给协作者带来构建摩擦；先通过 SBOM 记录当前镜像指纹，
  待正式 Release 时一次性固化。

## 5. 相关链接

- Dependabot 配置：`.github/dependabot.yml`
- 分支保护：`.github/BRANCH_PROTECTION.md`
- 发布流程：`.github/workflows/release.yml`
