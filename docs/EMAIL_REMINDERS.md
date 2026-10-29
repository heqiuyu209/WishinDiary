# 邮箱与预测提醒

## 已验证邮箱

注册仍可只用账号和密码。可选邮箱在注册后发送验证码；登录后在设置中完成验证。已有账号可在设置里绑定邮箱。验证成功后，可以用邮箱或原账号登录。

- 验证码默认 10 分钟有效，至少间隔 60 秒重发，累计 5 次错误后必须重新发送。
- 库中保存带服务端密钥的验证码摘要，接口、审计日志不返回验证码。
- 邮箱变更和解绑都会关闭提醒；验证后仍需要用户主动开启。
- 提醒默认提前 2 天，可选 1/2/3 天，按用户设置的时区判断当天；已开始或已过期的预测不补发。

## 邮件服务

SMTP 默认关闭，不影响原账号注册登录。部署者在 `.env` 配置自己的邮件服务：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-account
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@your-domain.example
SMTP_SECURITY=starttls
PUBLIC_WEB_URL=https://your-app.example
```

587 常用 STARTTLS；465 使用 `SMTP_SECURITY=ssl`。生产环境拒绝明文传输 `none`。密钥只保存在部署环境，不提交 Git。邮件服务是否接受发件域名、送达率与 DNS 配置需要用实际服务验证。

API：

| 操作 | 接口 |
| --- | --- |
| 当前账号的邮箱与提醒状态 | `GET /api/v1/notifications/settings` |
| 发起邮箱验证 | `POST /api/v1/notifications/email/request` |
| 输入验证码 | `POST /api/v1/notifications/email/verify` |
| 设置开关、提前天数、时区 | `PUT /api/v1/notifications/settings` |
| 解绑并关闭提醒 | `DELETE /api/v1/notifications/email` |

邮箱操作由当前登录身份决定，不接受其他账号 ID。用户删除账号时，验证记录与提醒记录通过外键级联删除。

## 逐步交付

- [x] 验证绑定、可选邮箱注册、已验证邮箱登录和偏好接口。
- [x] 用户设置页面与登录续期。
- [x] 定时提醒执行器、持久防重复；测试使用隔离 SMTP 接收器。

提醒邮件使用通用标题和登录链接，邮件正文不包含预测日期、症状或日记。

## 执行提醒

先迁移数据库、配置 SMTP，并让用户验证邮箱和主动开启提醒。执行器复用现有预测服务，不在请求中训练模型。

```bash
cd wishindiary-api
alembic upgrade head
python scripts/send_reminders.py --dry-run  # 默认模式，只输出数量，不发送或写预测/提醒记录
python scripts/send_reminders.py --send     # 检查并发送本轮到期提醒
python scripts/send_reminders.py --send --loop  # 每 5 分钟检查一次，支持 SIGTERM/SIGINT 停止
```

也可通过系统定时任务每 5 分钟执行一次 `--send`。只在当地提醒日当天发送，不补发停机期间已过期的提醒；模型重新预测后才决定是否到期，不提前保存固定日期任务。

Docker Compose 默认不开启执行器。配置好根目录 `.env` 后使用：

```bash
docker compose --profile reminders up -d --build
```

`reminders` 等待 API 健康检查通过（含迁移）。API 和执行器使用相同数据库、密钥和模型；执行器不开放端口。独立运行时必须先迁移数据库。

## 防重复与失败处理

发送前再次检查用户开关、验证邮箱、时区、提前天数和最新周期。按“用户 + 周期开始日”建立唯一记录，并在 SMTP 调用前提交 `sending` 状态；并发执行器和预测日期变化都不会导致同一周期重发。

| 状态 | 含义 | 后续处理 |
| --- | --- | --- |
| `sent` | SMTP 服务已接受邮件 | 本周期不再发送；不等于保证到达收件箱 |
| `unknown` | SMTP 返回失败，是否已接受无法确定 | 保留记录，不自动重发；查邮件服务日志 |
| `sending` | 已占用发送机会；进程可能中断 | 不自动重发；先核查执行器和服务商日志 |
| `canceled` | 发送前用户设置或最新周期已变化 | 本周期不再发送，避免过期提醒 |

SMTP 无法提供严格的“恰好一次送达”。本实现优先避免重复；极端故障可能漏发。不要直接删除 `unknown/sending` 记录重试；须先核查是否已经发送。管理端只提供这些状态的汇总数量，不暴露邮箱。

日常运维应保留最近发送状态并检查错误计数。执行器标准输出只包含模式和数量，不包含邮箱、验证码、用户 ID 或健康日期。真实发件域名的认证、投递和退信仍需部署者验证。
