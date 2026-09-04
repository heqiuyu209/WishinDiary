# WishinDiary 生产环境 TLS 终止方案

> 目标：在正式部署中以 443/HTTPS 向用户提供服务，同时在边界统一终止 TLS，
> 使后端 API 与前端静态资源只在内网/回环上传输 HTTP，简化证书管理并减小
> 攻击面。本文为 **docs/DEPLOYMENT.md「方案二」** 的 TLS 专项补充。

## 1. 架构

```
用户浏览器
   │  HTTPS 443（TLS 在此终止）
   ▼
Nginx（边界代理，持有证书私钥）
   ├── /api/*  ──HTTP 127.0.0.1:8000──▶  Uvicorn (FastAPI, --proxy-headers)
   └── 静态资源 ──直接从 /var/www/wishindiary 提供──▶  Vue 构建产物
```

要点：

- **TLS 只存在于 Nginx 与客户端之间**；证书私钥仅 Nginx 可读，不会进入容器。
- API 进程只监听 `127.0.0.1`，不直接暴露端口；Uvicorn 使用
  `--proxy-headers --forwarded-allow-ips=127.0.0.1` 信任 Nginx 转发的
  `X-Forwarded-Proto`，从而在重定向/链接中保持 `https://`。
- 数据库（MySQL）仅监听内网，不与公网直连。

## 2. 方案选型对比

| 方案 | 适合场景 | 优点 | 注意点 |
| --- | --- | --- | --- |
| **Nginx + Certbot**（本方案） | 单机/VM 部署 | 生态成熟、文档多、免费证书续期简单 | 需自行维护 nginx 配置与 systemd |
| Caddy | 极简部署 | 自动申请+续期证书、配置量最小 | 对自定义上游头/静态资源控制略少 |
| Traefik | Docker/K8s 编排 | 与容器发现集成好 | 单机场景偏重 |
| 云负载均衡（SLB/ALB）+ CDN | 云上多机 | 可叠加 WAF/CDN | 需在云控制台管理证书 |

本仓库提供 **Nginx** 模板：`deploy/nginx-tls.conf.example`。

## 3. 部署步骤（以 Ubuntu + systemd + Nginx 为例）

前置：已完成 docs/DEPLOYMENT.md 方案二中的「systemd 服务」与「Nginx 反向代理」，
API 监听 `127.0.0.1:8000` 且带 `--proxy-headers`。

1. **安装 certbot 并申请证书**（需 DNS 已指向服务器）：

```bash
sudo apt update && sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d diary.example.com
sudo certbot renew --dry-run
```

2. **替换站点配置为 TLS 模板**：

```bash
sudo cp deploy/nginx-tls.conf.example /etc/nginx/sites-available/wishindiary
# 编辑：把 diary.example.com 全部替换为真实域名（含证书路径）
sudo nginx -t
sudo systemctl reload nginx
```

3. **确认应用侧配置**（docs/DEPLOYMENT.md 环境变量表）：

```dotenv
ENVIRONMENT=production
CORS_ORIGINS=https://diary.example.com
```

4. **重启并验证**：

```bash
sudo systemctl restart wishindiary-api
curl --fail https://diary.example.com/api/health
curl -sI https://diary.example.com/ | grep -i strict-transport-security
```

## 4. 安全基线清单

执行 `curl -sI https://<域名>/` 并核对：

- [x] 响应头含 `Strict-Transport-Security`（HSTS）
- [x] 响应头含 `X-Content-Type-Options: nosniff`
- [x] `X-Frame-Options: DENY`（防点击劫持）
- [x] `Referrer-Policy` 与 `Permissions-Policy` 已设置
- [x] `TLS >= 1.2`，证书有效期 > 30 天
- [x] HTTP(80) 自动 301 跳转到 HTTPS
- [x] 私钥权限 `600`、路径仅在 Nginx 配置可见

可使用 [SSL Labs](https://www.ssllabs.com/ssltest/) 或
`openssl s_client -connect <域名>:443` 复核证书链。

## 5. 证书续期

Certbot 默认通过 systemd timer 每日自动续期，续期后会重载 nginx：

```bash
sudo systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

若使用 `--webroot` 校验方式，模板中的 `/.well-known/acme-challenge/` 与
`/var/www/certbot` 需保证可写可读。

## 6. 风险与建议

- **不要在公网直接暴露 8000 / 3306**：Nginx 是唯一入口。
- **日志最小化**：Nginx access log 中健康检查与登录路径会被高频记录，
  建议关闭 access_log 或按 `access_log off` 处理敏感路径（模板未默认关闭，
  可按需自行调整）。
- **健康数据合规**：用户日记/经期数据在传输层由 TLS 保护；存储层加密备份
  见 docs/BACKUP_DR.md。
