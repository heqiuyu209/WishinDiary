# 部署指南

本文给出两种部署方式：Docker Compose 适合单机快速部署；systemd + Nginx
适合希望自行管理 MySQL、进程和证书的 Linux 服务器。

> WishinDiary 会处理敏感健康数据。正式部署必须启用 HTTPS、限制数据库访问、
> 使用加密备份，并确保日志和监控中不记录密码、JWT 或用户日记正文。

## 方案一：Docker Compose

### 1. 准备配置并启动

Windows PowerShell：

```powershell
cd C:\path\to\WishinDiary
powershell -ExecutionPolicy Bypass -File .\scripts\setup_docker.ps1
docker compose config
docker compose up -d --build
docker compose ps
```

Linux/macOS：

```bash
cd /opt/WishinDiary
cp .env.example .env
chmod 600 .env
openssl rand -base64 32
# 将两个不同的随机密码和一个至少 32 字符的 SECRET_KEY 写入 .env
# 将 CORS_ORIGINS 改为实际 HTTPS 域名
docker compose config
docker compose up -d --build
docker compose ps
```

默认只有本机能访问 Web `http://127.0.0.1:8080` 和 API
`http://127.0.0.1:8000/api/health`。不要把 MySQL 3306 或 Uvicorn 8000
直接暴露到公网。

### 2. 日志与故障排查

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 db
docker compose logs -f frontend backend
```

健康检查成功时，API 返回 `{"status":"ok","database":"connected"}`。

### 3. 升级与回滚

升级前先备份数据库并记录当前提交：

```bash
git rev-parse HEAD
git pull --ff-only
docker compose build --pull
docker compose up -d
docker compose ps
```

若新版本失败，切换回刚才记录的已知正常提交，再重新构建。切换提交不会删除
命名卷中的 MySQL 数据；不要运行 `docker compose down -v`。

```bash
git switch --detach <known-good-commit>
docker compose up -d --build
```

### 4. 数据库备份与恢复

备份：

```bash
umask 077
docker compose exec -T db sh -c 'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' > wishindiary-backup.sql
```

备份文件包含敏感健康数据，禁止提交 Git。建议使用独立加密存储，并定期做恢复演练。

恢复会覆盖同名记录，必须先确认目标实例并停止 API 写入：

```bash
docker compose stop backend
docker compose exec -T db sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < wishindiary-backup.sql
docker compose start backend
curl --fail http://127.0.0.1:8000/api/health
```

## 方案二：Ubuntu + systemd + Nginx

以下示例假设：

- 仓库位于 `/opt/wishindiary`
- API 以受限用户 `wishindiary` 运行
- 已安装 Python 3.12、Node.js 22.18+、MySQL 8 和 Nginx
- 域名为 `diary.example.com`，请替换为你的真实域名
- MySQL 已创建最小权限用户并导入 `wishindiary-api/schema.sql`

### 1. 安装与构建

```bash
sudo useradd --system --create-home --home-dir /opt/wishindiary --shell /usr/sbin/nologin wishindiary
sudo chown -R wishindiary:wishindiary /opt/wishindiary

cd /opt/wishindiary/wishindiary-api
sudo -u wishindiary python3.12 -m venv .venv
sudo -u wishindiary .venv/bin/python -m pip install --upgrade pip
sudo -u wishindiary .venv/bin/python -m pip install -r requirements.txt

cd /opt/wishindiary/Wishindiary-web
npm ci
VITE_API_BASE_URL=/ npm run build
sudo install -d -o root -g www-data -m 0750 /var/www/wishindiary
sudo cp -a dist/. /var/www/wishindiary/
```

先创建配置目录：

```bash
sudo install -d -o root -g wishindiary -m 0750 /etc/wishindiary
```

在 `/etc/wishindiary/api.env` 写入生产配置，并限制读取权限：

```dotenv
ENVIRONMENT=production
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=wishin_app
DB_PASSWORD=<strong-random-database-password>
DB_NAME=wishindiary_db
SECRET_KEY=<at-least-32-random-characters>
CORS_ORIGINS=https://diary.example.com
MODEL_SHA256=6f01416b50834899aa60a803b5980ec9c1a25d9ed6f92d0a07559054756fc888
```

```bash
sudo chown root:wishindiary /etc/wishindiary/api.env
sudo chmod 0640 /etc/wishindiary/api.env
```

### 2. systemd 服务

创建 `/etc/systemd/system/wishindiary-api.service`：

```ini
[Unit]
Description=WishinDiary FastAPI service
After=network-online.target mysql.service
Wants=network-online.target

[Service]
Type=simple
User=wishindiary
Group=wishindiary
WorkingDirectory=/opt/wishindiary/wishindiary-api
EnvironmentFile=/etc/wishindiary/api.env
ExecStart=/opt/wishindiary/wishindiary-api/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

加载、启动并检查：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wishindiary-api
sudo systemctl status wishindiary-api --no-pager
sudo journalctl -u wishindiary-api -n 100 --no-pager
curl --fail http://127.0.0.1:8000/api/health
```

### 3. Nginx 反向代理

创建 `/etc/nginx/sites-available/wishindiary`：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name diary.example.com;

    root /var/www/wishindiary;
    index index.html;
    client_max_body_size 1m;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }

    location /assets/ {
        try_files $uri =404;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/wishindiary /etc/nginx/sites-enabled/wishindiary
sudo nginx -t
sudo systemctl reload nginx
```

### 4. HTTPS 与自动续期

确保 DNS 已指向服务器后安装 Certbot：

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d diary.example.com
sudo certbot renew --dry-run
```

Certbot 会修改 Nginx 配置并建立续期定时器。HTTPS 生效后，再确认
`CORS_ORIGINS=https://diary.example.com` 并重启 API：

```bash
sudo systemctl restart wishindiary-api
```

## 环境变量

| 变量 | 用途 | 生产要求 |
| --- | --- | --- |
| `ENVIRONMENT` | `development` / `production` | 必须为 `production` |
| `DB_HOST` / `DB_PORT` | MySQL 地址 | 使用本机或内网地址 |
| `DB_USER` / `DB_PASSWORD` | 应用数据库账号 | 最小权限、强随机密码 |
| `DB_ROOT_PASSWORD` | Compose 初始化 root 密码 | 仅 Compose 使用，不传给 API |
| `DB_NAME` | 数据库名 | 使用独立数据库 |
| `SECRET_KEY` | JWT 签名密钥 | 至少 32 个随机字符 |
| `CORS_ORIGINS` | 允许的前端来源 | 仅填实际 HTTPS 来源，禁止 `*` |
| `MODEL_SHA256` | `.skops` 文件哈希 | 必须与发布模型一致 |
| `API_PORT` / `WEB_PORT` | Compose 本机绑定端口 | 按需修改，避免公网监听 |

## 上线后检查

```bash
curl --fail https://diary.example.com/api/health
curl -I https://diary.example.com/
```

同时验证注册、登录、历史周期、预测日期、日志记录和退出登录。不要使用真实用户数据
执行调试；生产日志的保留周期应尽可能短，并限制管理员访问。
