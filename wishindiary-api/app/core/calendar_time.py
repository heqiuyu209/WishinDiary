"""Account-local calendar dates and UTC event instants."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.errors import AppError

DEFAULT_TIMEZONE = "Asia/Shanghai"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calendar_today(timezone_name: str = DEFAULT_TIMEZONE):
    return utc_now().astimezone(ZoneInfo(timezone_name)).date()


def user_today(cursor, user_id: int):
    cursor.execute("SELECT notification_timezone FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    if user is None:
        raise AppError(404, "not_found", "账号不存在")
    return calendar_today(user["notification_timezone"])
