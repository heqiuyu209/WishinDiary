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
- [ ] 用户设置页面与登录续期。
- [ ] 定时提醒执行器、持久防重复、真实传输模拟验证。

提醒邮件使用通用标题和登录链接，邮件正文不包含预测日期、症状或日记。
