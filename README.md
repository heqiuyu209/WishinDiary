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
├── wishindiary-api/              # FastAPI 后端、schema、模型和测试
│   ├── app/                      # core、features、ml、repositories、routers、services
│   ├── ml/menstrual_rf_model.skops
│   ├── scripts/                  # 本地配置、训练、模型检查
│   ├── tests/
│   └── schema.sql
├── Wishindiary-web/              # Vue 3 前端
├── docker-compose.yml            # MySQL + API + Nginx Web
├── scripts/setup_docker.ps1      # 自动生成 Docker 本地密钥
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

容器默认只绑定本机地址：Web `127.0.0.1:8080`，API `127.0.0.1:8000`，不会直接暴露到公网。

### Windows PowerShell

```powershell
cd C:\path\to\WishinDiary
powershell -ExecutionPolicy Bypass -File .\scripts\setup_docker.ps1
docker compose up -d --build
docker compose ps
```

打开 <http://127.0.0.1:8080>。

### Linux/macOS

```bash
cd /path/to/WishinDiary
cp .env.example .env
openssl rand -base64 32
# 编辑 .env，填写 DB_PASSWORD、DB_ROOT_PASSWORD、SECRET_KEY
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

首次初始化空数据库时执行：

```sql
SOURCE C:/path/to/WishinDiary/wishindiary-api/schema.sql;
```

### 常见启动问题：模型版本警告

如果日志出现 `InconsistentVersionWarning`，说明启动时使用的 Python 环境中的
scikit-learn 版本与发布模型的训练版本不一致。请使用项目虚拟环境安装锁定依赖，
不要直接使用系统 Python 启动：

```powershell
cd C:\path\to\WishinDiary
.\.venv\Scripts\python.exe -m pip install -r .\wishindiary-api\requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\wishindiary-api --reload --host 127.0.0.1 --port 8000
```

发布模型当前按 `requirements.txt` 中锁定的 scikit-learn 版本训练。若你有意升级
scikit-learn，请重新训练模型、运行 `scripts\inspect_model.py`，并重新确认模型哈希。

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

仓库已提供 `wishindiary-api/ml/menstrual_rf_model.skops`。它使用固定随机种子的纯合成周期数据训练，不读取真实用户数据库。

模型信息和 SHA-256 位于 [MODEL_CARD.md](MODEL_CARD.md)。重新训练和检查：

```powershell
cd C:\path\to\WishinDiary\wishindiary-api
..\.venv\Scripts\python.exe scripts/train.py --synthetic-only
..\.venv\Scripts\python.exe scripts/inspect_model.py
```

重新训练后必须更新 `MODEL_SHA256`；生产环境不会加载哈希不匹配的模型。

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

## 开源贡献
请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目使用 [MIT License](LICENSE)。模型和第三方依赖的许可证与来源请以 [MODEL_CARD.md](MODEL_CARD.md) 及各自上游项目为准。
