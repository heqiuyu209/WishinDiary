"""Timezone-aware reminders with durable, conservative SMTP send claims.

A claim commits before SMTP. A process crash or uncertain SMTP acknowledgement
must never lead to an automatic resend for the same cycle.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pymysql

from app.core.config import settings
from app.core.database import transaction
from app.core.email import MailDeliveryError, send_email
from app.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReminderPlan:
    user_id: int
    cycle_start: date
    predicted_date: date
    reminder_date: date
    lead_days: int
    timezone: str
    email: str


def plan_reminder(user: dict, prediction: dict, now: datetime) -> ReminderPlan | None:
    if now.tzinfo is None:
        raise ValueError("Reminder clock must have a timezone")
    if not user.get("email") or not user.get("email_verified_at") or not user.get("reminder_enabled"):
        return None
    if prediction.get("status") != "success" or not prediction.get("prediction"):
        return None
    try:
        result = prediction["prediction"]
        start = date.fromisoformat(result["last_period_start"])
        predicted = date.fromisoformat(result["next_period_start"])
        lead = int(user["reminder_lead_days"])
        today = now.astimezone(ZoneInfo(user["notification_timezone"])).date()
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError):
        return None
    due = predicted - timedelta(days=lead)
    if lead not in (1, 2, 3) or start > today or predicted <= today or due != today:
        return None
    return ReminderPlan(user["user_id"], start, predicted, due, lead,
                        user["notification_timezone"], user["email"])


def _locked_user(cursor, plan: ReminderPlan, now: datetime) -> bool:
    cursor.execute("""
        SELECT user_id, email, email_verified_at, reminder_enabled, reminder_lead_days,
               notification_timezone FROM users WHERE user_id=%s FOR UPDATE
    """, (plan.user_id,))
    user = cursor.fetchone()
    if not user:
        return False
    snapshot = {"status": "success", "prediction": {
        "last_period_start": plan.cycle_start.isoformat(),
        "next_period_start": plan.predicted_date.isoformat(),
    }}
    if plan_reminder(user, snapshot, now) != plan:
        return False
    # Lock the latest cycle and insertion range until send completes. A newly
    # recorded start invalidates this plan, even if prediction ran earlier.
    cursor.execute("SELECT start_date FROM cycles WHERE user_id=%s ORDER BY start_date DESC LIMIT 1 FOR UPDATE",
                   (plan.user_id,))
    cycle = cursor.fetchone()
    return bool(cycle and cycle["start_date"] == plan.cycle_start)


class ReminderService:
    def __init__(self, predictor: PredictionService | None = None) -> None:
        self.predictor = predictor

    def _already_claimed(self, plan: ReminderPlan) -> bool:
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT delivery_id FROM reminder_deliveries WHERE user_id=%s AND cycle_start_date=%s",
                               (plan.user_id, plan.cycle_start))
                return cursor.fetchone() is not None

    def _claim(self, plan: ReminderPlan, now: datetime) -> int | None:
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    if not _locked_user(cursor, plan, now):
                        return None
                    cursor.execute("""
                        INSERT INTO reminder_deliveries
                          (user_id, cycle_start_date, predicted_date, reminder_date, state, created_at)
                        VALUES (%s, %s, %s, %s, 'sending', %s)
                    """, (plan.user_id, plan.cycle_start, plan.predicted_date,
                           plan.reminder_date, now.astimezone(timezone.utc).replace(tzinfo=None)))
                    delivery_id = cursor.lastrowid
            return delivery_id
        except pymysql.err.IntegrityError as error:
            if error.args[0] == 1062:
                return None
            raise

    def _send_claimed(self, delivery_id: int, plan: ReminderPlan, now: datetime) -> str:
        with transaction() as connection:
            with connection.cursor() as cursor:
                valid = _locked_user(cursor, plan, now)
                cursor.execute("SELECT state FROM reminder_deliveries WHERE delivery_id=%s FOR UPDATE", (delivery_id,))
                row = cursor.fetchone()
                if not row or row["state"] != "sending":
                    return "skipped"
                outcome = "canceled"
                if valid:
                    try:
                        send_email(plan.email, "WishinDiary 提醒",
                                   "你设置的提醒时间到了，请登录查看最新信息。\n"
                                   f"{settings.PUBLIC_WEB_URL.rstrip('/')}/settings\n"
                                   "预测仅供参考，可在设置中随时关闭提醒或解绑邮箱。")
                        outcome = "sent"
                    except MailDeliveryError:
                        # A transport error may happen after the server accepted
                        # the mail. Keep the claim and require operator review.
                        outcome = "unknown"
                cursor.execute("UPDATE reminder_deliveries SET state=%s, sent_at=%s WHERE delivery_id=%s",
                               (outcome, now.astimezone(timezone.utc).replace(tzinfo=None) if outcome == "sent" else None,
                                delivery_id))
        return outcome

    def run_once(self, *, send: bool = False, now: datetime | None = None) -> dict:
        if send and not settings.mail_enabled:
            raise MailDeliveryError("Mail service is not configured")
        if now is not None and now.tzinfo is None:
            raise ValueError("Reminder clock must have a timezone")
        counts = {key: 0 for key in ("checked", "due", "sent", "unknown", "canceled", "skipped", "errors")}
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT user_id, email, email_verified_at, reminder_enabled, reminder_lead_days,
                           notification_timezone FROM users
                    WHERE reminder_enabled=1 AND email_verified_at IS NOT NULL AND email IS NOT NULL
                """)
                users = cursor.fetchall()
        if users and self.predictor is None:
            self.predictor = PredictionService()
        for user in users:
            counts["checked"] += 1
            try:
                prediction = self.predictor.get_prediction(user["user_id"], record=False)
                current_time = now or datetime.now(timezone.utc)
                plan = plan_reminder(user, prediction, current_time)
                if plan is None or self._already_claimed(plan):
                    counts["skipped"] += 1
                    continue
                counts["due"] += 1
                if send:
                    claim = self._claim(plan, now or datetime.now(timezone.utc))
                    outcome = self._send_claimed(claim, plan, now or datetime.now(timezone.utc)) if claim is not None else "skipped"
                    counts[outcome] += 1
            except Exception:
                # No recipient, health date, or exception text in batch logs.
                logger.error("Reminder processing failed; inspect delivery states before retrying")
                counts["errors"] += 1
        return counts
