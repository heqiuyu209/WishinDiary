"""Verified email binding and explicit, user-controlled notification settings."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

import pymysql

from app.core.audit import audit
from app.core.config import settings
from app.core.database import transaction
from app.core.email import MailDeliveryError, send_email
from app.core.errors import AppError
from app.schemas.notifications import NotificationPreferences


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _code_hash(user_id: int, email: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{user_id}:{email}:{code}".encode(), hashlib.sha256).hexdigest()


class NotificationService:
    def get_settings(self, user_id: int) -> dict:
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT email, email_verified_at, reminder_enabled, reminder_lead_days,
                           notification_timezone FROM users WHERE user_id = %s
                """, (user_id,))
                user = cursor.fetchone()
                if not user:
                    raise AppError(404, "not_found", "账号不存在")
                cursor.execute("SELECT pending_email FROM email_verifications WHERE user_id = %s", (user_id,))
                pending = cursor.fetchone()
                cursor.execute("SELECT state FROM reminder_deliveries WHERE user_id = %s ORDER BY created_at DESC LIMIT 1", (user_id,))
                last = cursor.fetchone()
        return {"status": "success", "email": user["email"],
                "email_verified": user["email_verified_at"] is not None,
                "pending_email": pending["pending_email"] if pending else None,
                "enabled": bool(user["reminder_enabled"]), "lead_days": user["reminder_lead_days"],
                "timezone": user["notification_timezone"], "mail_available": settings.mail_enabled,
                "last_delivery_state": last["state"] if last else None}

    def request_verification(self, user_id: int, email: str) -> dict:
        if not settings.mail_enabled:
            raise AppError(503, "mail_unavailable", "邮箱服务尚未启用，可暂不填写邮箱")
        email = email.strip().lower()
        now = _utc_now()
        code = f"{secrets.randbelow(1_000_000):06d}"
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                if not cursor.fetchone():
                    raise AppError(404, "not_found", "账号不存在")
                cursor.execute("SELECT sent_at FROM email_verifications WHERE user_id = %s", (user_id,))
                pending = cursor.fetchone()
                if pending and (now - pending["sent_at"]).total_seconds() < 60:
                    raise AppError(429, "rate_limited", "请等待 60 秒后再发送验证码")
                cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id <> %s", (email, user_id))
                if cursor.fetchone():
                    raise AppError(409, "email_unavailable", "该邮箱不可用，请使用其他邮箱")
                cursor.execute("""
                    INSERT INTO email_verifications (user_id, pending_email, code_hash, expires_at, sent_at, attempts)
                    VALUES (%s, %s, %s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE pending_email=VALUES(pending_email), code_hash=VALUES(code_hash),
                      expires_at=VALUES(expires_at), sent_at=VALUES(sent_at), attempts=0
                """, (user_id, email, _code_hash(user_id, email, code),
                       now + timedelta(minutes=settings.EMAIL_VERIFICATION_MINUTES), now))
                cursor.execute("UPDATE users SET reminder_enabled = 0 WHERE user_id = %s", (user_id,))
                try:
                    send_email(email, "WishinDiary 邮箱验证",
                               f"你的验证码是：{code}\n{settings.EMAIL_VERIFICATION_MINUTES} 分钟内有效。\n如果不是你发起的请求，可以忽略此邮件。")
                except MailDeliveryError:
                    raise AppError(503, "mail_unavailable", "验证码发送失败，请稍后重试") from None
        audit("email.verification.requested", actor_user_id=user_id, success=True)
        return {"status": "success", "message": "验证码已发送，请查收", "resend_after_seconds": 60}

    def verify_email(self, user_id: int, code: str) -> dict:
        error = None
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT user_id FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                    cursor.execute("SELECT * FROM email_verifications WHERE user_id = %s FOR UPDATE", (user_id,))
                    row = cursor.fetchone()
                    if not row or row["expires_at"] <= _utc_now() or row["attempts"] >= 5:
                        raise AppError(400, "invalid_code", "验证码已失效，请重新发送")
                    if not hmac.compare_digest(row["code_hash"], _code_hash(user_id, row["pending_email"], code)):
                        cursor.execute("UPDATE email_verifications SET attempts = attempts + 1 WHERE user_id = %s", (user_id,))
                        error = AppError(400, "invalid_code", "验证码错误")
                    else:
                        cursor.execute("UPDATE users SET email=%s, email_verified_at=%s, reminder_enabled=0 WHERE user_id=%s",
                                       (row["pending_email"], _utc_now(), user_id))
                        cursor.execute("DELETE FROM email_verifications WHERE user_id = %s", (user_id,))
        except pymysql.err.IntegrityError:
            raise AppError(409, "email_unavailable", "该邮箱不可用，请使用其他邮箱") from None
        # Raise after commit so incorrect-attempt counters cannot roll back.
        if error:
            raise error
        audit("email.verified", actor_user_id=user_id, success=True)
        return {"status": "success", "message": "邮箱验证成功，可在设置中开启提醒"}

    def update_preferences(self, user_id: int, preferences: NotificationPreferences) -> dict:
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT email_verified_at FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                user = cursor.fetchone()
                if not user:
                    raise AppError(404, "not_found", "账号不存在")
                if preferences.enabled and not user["email_verified_at"]:
                    raise AppError(400, "email_not_verified", "请先绑定并验证邮箱")
                if preferences.enabled and not settings.mail_enabled:
                    raise AppError(503, "mail_unavailable", "邮箱服务尚未启用")
                cursor.execute("UPDATE users SET reminder_enabled=%s, reminder_lead_days=%s, notification_timezone=%s WHERE user_id=%s",
                               (preferences.enabled, preferences.lead_days, preferences.timezone, user_id))
        return {"status": "success", "message": "提醒设置已保存"}

    def unbind_email(self, user_id: int) -> dict:
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE users SET email=NULL, email_verified_at=NULL, reminder_enabled=0 WHERE user_id=%s", (user_id,))
                cursor.execute("DELETE FROM email_verifications WHERE user_id=%s", (user_id,))
        audit("email.unbound", actor_user_id=user_id, success=True)
        return {"status": "success", "message": "邮箱已解绑，提醒已关闭"}
