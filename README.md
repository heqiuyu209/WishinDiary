# WishinDiary

注重隐私的生理周期与健康日志应用，提供周期记录、趋势看板、健康报告和本地随机森林预测。

> 本项目是健康记录与实验性预测工具，不是医疗器械，不提供诊断、治疗、避孕或紧急医疗建议。出现持续疼痛、异常出血或其他担忧时，请咨询专业医务人员。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 功能

- JWT 登录、登出与多用户数据隔离
- 周期开始/结束记录、历史区间修正和误标删除
- 日历区间标记、未来周期预测、排卵日和易孕窗口展示
- 每日情绪、腹痛、运动、饮食、同房和日记记录
- 统计看板与结构化健康报告
- 安全 `.skops` 模型加载、SHA-256 校验和特征契约检查
- 纯合成数据训练脚本，不需要读取真实用户数据
- FastAPI + MySQL + Vue 3，可本地运行或 Docker Compose 部署

## 技术栈

| 层 | 技术 |
| --- | --- |
| API | Python 3.12、FastAPI、Uvicorn、PyMySQL |
| 数据库 | MySQL 8.0 |
| 认证 | bcrypt、PyJWT、HttpOnly Cookie |
| 机器学习 | NumPy、Pandas、scikit-learn、skops |
| Web | Node.js 22.18+、Vue 3、Vite、Pinia、Axios、V-Calendar、ECharts |
| 部署 | Docker Compose、Nginx |

## 目录

```text
WishinDiary/
├── wishindiary-api/              # FastAPI 后端、迁移、模型和测试
│   ├── app/                      # core、features、ml、repositories、routers、services
│   ├── migrations/               # Alembic 数据库迁移（含版本历史与回滚）
│   ├── ml/                      # 本地生成的预测模型目录（*.skops 不入库）
│   ├── scripts/                  # 本地配置、训练、模型检查、备份恢复、数据清理
│   └── tests/
├── Wishindiary-web/              # Vue 3 前端
├── docker-compose.yml            # MySQL + API + Nginx Web
├── scripts/setup_docker.ps1      # 自动生成 Docker 本地密钥
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── MODEL_CARD.md
├── SECURITY.md
└── LICENSE
```

## 运行前要求

- Windows 10/11、Linux 或 macOS
- Python 3.12、Node.js 22.18+
- MySQL 8.0+（本地开发需要；Docker 会自动启动）
- Docker Desktop（容器部署需要）

## Docker Compose（推荐）

Web 默认监听 `0.0.0.0:8080`，云服务器可通过 IP:端口访问（需放行安全组与防火墙的 TCP 8080）。API 仍只绑定 `127.0.0.1:8000`，MySQL 不映射宿主机端口；网页的 `/api/` 请求由前端 Nginx 转发。

Docker 中认证 Cookie 默认要求 HTTPS。通过 HTTP 的 IP:端口调试时，先在根目录 `.env` 设置 `ALLOW_INSECURE_HTTP=true`，并将 `CORS_ORIGINS` 设为实际访问地址，例如 `http://服务器IP:8080`。正式 HTTPS 部署恢复为 `false`；宿主机有反向代理时可设 `WEB_BIND_HOST=127.0.0.1`，仅由代理提供公网入口。

### Windows PowerShell

> 首次使用请先构建后端虚拟环境并生成模型（仓库不附带预训练模型，见 [MODEL_CARD.md](MODEL_CARD.md)）：

```powershell
cd C:\path\to\WishinDiary
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\wishindiary-api\requirements.txt
.\.venv\Scripts\python.exe .\wishindiary-api\scripts\train.py --synthetic-only
```

然后生成 Docker 配置并启动：

```powershell
cd C:\path\to\WishinDiary
powershell -ExecutionPolicy Bypass -File .\scripts\setup_docker.ps1
# 编辑 .env；本地 HTTP 调试设置 ALLOW_INSECURE_HTTP=true
docker compose up -d --build
docker compose ps
```

> `setup_docker.ps1` 会校验模型文件，若缺失会自动调用训练脚本生成（详见脚本注释）。

打开 <http://127.0.0.1:8080>。

### Linux/macOS

> 首次使用请先构建后端虚拟环境并生成模型（仓库不附带预训练模型，见 [MODEL_CARD.md](MODEL_CARD.md)）：

```bash
cd /path/to/WishinDiary
python3 -m venv .venv
.venv/bin/pip install -r wishindiary-api/requirements.txt
.venv/bin/python wishindiary-api/scripts/train.py --synthetic-only
```

然后生成 Docker 配置并启动：

```bash
cd /path/to/WishinDiary
cp .env.example .env
openssl rand -base64 32
# 编辑 .env，填写 DB_PASSWORD、DB_ROOT_PASSWORD、SECRET_KEY
# 将 sha256sum wishindiary-api/ml/menstrual_rf_model.skops 的哈希填入 MODEL_SHA256
# HTTP 调试设置 ALLOW_INSECURE_HTTP=true，并填写实际 CORS_ORIGINS
docker compose up -d --build
docker compose ps
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

成功响应包含 `{"status":"ok","database":"connected"}`。停止服务：

```bash
docker compose down
```

只停止容器但保留数据库卷：

```bash
docker compose stop
```

> 不要执行 `docker compose down -v`，除非你明确要删除本地数据库卷及其中的数据。

## Windows 本地开发

### 1. 安装后端依赖

```powershell
cd C:\path\to\WishinDiary
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\wishindiary-api\requirements-dev.txt
```

### 2. 配置 MySQL

确保 MySQL80 服务已启动，并准备现有 MySQL 用户密码。配置脚本只读测试连接、查询用户数量并生成随机 JWT 密钥，不会删除或重建表：

```powershell
powershell -ExecutionPolicy Bypass -File .\wishindiary-api\scripts\setup_local.ps1 -DbUser root -DbName wishindiary_db
```

首次初始化空数据库时，使用 Alembic 迁移建表（数据库结构统一由
`wishindiary-api/migrations/` 管理）：

```powershell
cd C:\path\to\WishinDiary\wishindiary-api
..\.venv\Scripts\python.exe -m alembic upgrade head
```

### 常见启动问题：模型版本警告

如果日志出现 `InconsistentVersionWarning`，说明启动时使用的 Python 环境中的
scikit-learn 版本与当前模型的训练版本不一致（模型由本地训练生成）。请使用项目虚拟环境安装锁定依赖，
不要直接使用系统 Python 启动：

```powershell
cd C:\path\to\WishinDiary
.\.venv\Scripts\python.exe -m pip install -r .\wishindiary-api\requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\wishindiary-api --reload --host 127.0.0.1 --port 8000
```

本地训练生成模型时按 `requirements.txt` 中锁定的 scikit-learn 版本进行。若你有意升级
scikit-learn，请重新训练模型、运行 `scripts\inspect_model.py`，并同步更新 `MODEL_SHA256`。

当前 `requirements.txt` 锁定 **scikit-learn 1.5.2**；已在 **1.9.0 + skops 0.11.0**
组合下实测：同一份模型两个版本加载与推理结果一致。使用方式二选一：

- **官方默认（无警告）**：按 `requirements.txt` 安装（scikit-learn==1.5.2、skops==0.14.0）。
- **自愿升级 1.9.0**：`pip install scikit-learn==1.9.0 skops==0.11.0`。推理正常，仅启动加载时打印
  一条一次性的 `InconsistentVersionWarning`，可忽略。若升级后重训模型，请同步更新
  `MODEL_SHA256` 与本段说明。

### 3. 启动 API

```powershell
cd C:\path\to\WishinDiary\wishindiary-api
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI：<http://127.0.0.1:8000/docs>。

### 4. 启动 Web

```powershell
cd C:\path\to\WishinDiary\Wishindiary-web
Copy-Item .env.example .env -Force
npm ci
npm run dev
```

打开 <http://localhost:5173>。

### 5. 登录只读验证

```powershell
cd C:\path\to\WishinDiary
powershell -ExecutionPolicy Bypass -File .\wishindiary-api\scripts\test_login.ps1
```

这个脚本不会注册、修改或删除用户。

## 机器学习模型

仓库**不附带预训练模型文件**。模型由
`wishindiary-api/scripts/train.py` 用固定随机种子的纯合成周期数据（或你自己的授权数据）生成到
`wishindiary-api/ml/` 下，不读取真实用户数据库。

生成与检查模型：

```powershell
cd C:\path\to\WishinDiary\wishindiary-api
..\.venv\Scripts\python.exe scripts/train.py --synthetic-only
..\.venv\Scripts\python.exe scripts/inspect_model.py
```

生成后 `wishindiary-api/ml/menstrual_rf_model.skops` 即被应用加载。开发环境若未生成模型，
预测接口以"无模型基线预测"降级运行（日志有告警）；生产环境则拒绝启动。模型信息与 SHA-256
约定见 [MODEL_CARD.md](MODEL_CARD.md)——重新训练后必须把产出的 hash 更新到 `MODEL_SHA256`，
生产环境不会加载哈希不匹配的模型。

## 测试与质量门禁

```powershell
cd C:\path\to\WishinDiary\wishindiary-api
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check app scripts tests

cd ..\Wishindiary-web
npm ci
npm run build
npm audit --audit-level=high
```

GitHub Actions 会在 push 和 pull request 时运行后端测试、Ruff、pip-audit、
npm audit 和前端构建。

## Linux 生产部署建议

生产环境不要直接把 Uvicorn 或 MySQL 端口暴露到公网。建议：

1. 使用 Docker Compose 或 systemd 管理 API 进程。
2. 使用 Nginx/Caddy 终止 TLS，并将 `/api/` 代理到 API。
3. 将 `CORS_ORIGINS` 设置为实际 HTTPS 前端域名，不使用 `*`。
4. `ENVIRONMENT=production` 时使用至少 32 字符随机 `SECRET_KEY` 和强数据库密码。
5. 限制 MySQL 仅在内部网络监听，定期执行加密备份和恢复演练。
6. 备份文件不要放在 Git 工作区。

详细教程见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)，发布前检查见
[docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)。

## 数据与隐私

周期、症状、同房记录和日记属于敏感健康数据。请只在自己控制的环境中部署，使用 HTTPS、访问控制、加密备份和明确的数据删除策略。请阅读 [SECURITY.md](SECURITY.md)。

数据生命周期接口与脚本：

- **导出**：`GET /api/v1/user/export` 返回当前用户的全部健康数据（用户资料、周期、每日日志、预测记录），用于数据可携带与个人备份。
- **删除**：`DELETE /api/v1/user/me` 在单个事务中删除当前账号及其全部关联数据（级联清理，含外键 CASCADE 兜底）。
- **保留期限**：环境变量 `DATA_RETENTION_DAYS`（0 表示无限期保留，默认）；设置 >0 后可运行 `wishindiary-api/scripts/cleanup_expired_data.py` 定期清理过期数据。
- **备份与恢复**：`wishindiary-api/scripts/backup_database.sh` / `restore_database.sh`（支持 Docker Compose 与本地 MySQL），详细说明见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) 与 [docs/DATA_LIFECYCLE.md](docs/DATA_LIFECYCLE.md)。

## 功能演示

> 说明：仓库暂未提供界面截图。如需体验界面，请按上文的 Docker Compose 
> 或本地开发章节在本机部署，以下功能可直接体验，后续会更新界面截图（现在感觉界面做得不好看）：

- **登录/注册**：注册账号登录后凭 HttpOnly Cookie 保持会话。
- **日历周期记录与预测**：记录经期开始/结束日期，基于随机森林模型生成周期预测。
- **统计看板**：查看周期趋势与健康指标统计。
- **健康报告**：生成结构化健康报告。

界面数据为合成或本地自测数据，不含任何真实用户信息；模型与数据口径见 [MODEL_CARD.md](MODEL_CARD.md)。

> 在线 Demo：为避免真实健康数据风险，本项目不提供公共在线 Demo；如需体验，请按上文 Docker Compose 在本机部署。

## 开源贡献
请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，其中包含维护者名单与问题响应范围。发生不当行为或安全问题时的举报渠道见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) 与 [SECURITY.md](SECURITY.md)。

## 支持与反馈

- 问题与功能建议：请在仓库提交 issue（有 Bug / 功能 / 咨询三类模板）。
- 安全漏洞：请通过 SECURITY.md 中描述的私有渠道报告，不要公开提交。
- 日常使用与部署问题：可先查阅 `docs/` 目录（部署、数据生命周期、发布前检查）。
- 响应范围与维护节奏见 CONTRIBUTING.md 的"维护者与问题响应范围"段。

## 许可证

本项目使用 [MIT License](LICENSE)。模型和第三方依赖的许可证与来源请以 [MODEL_CARD.md](MODEL_CARD.md) 及各自上游项目为准。
