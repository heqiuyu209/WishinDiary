"""As-recorded cycle geometry; derived labels must respect these UTC events."""
from datetime import timezone

from app.core.calendar_time import utc_now


def record_cycle_revisions(cursor, user_id: int, *, source: str = "user_recorded") -> None:
    if source not in {"user_recorded", "repair_snapshot", "retention_snapshot"}:
        raise ValueError("Unsupported cycle revision source")
    cursor.execute("SELECT cycle_id,start_date,end_date FROM cycles WHERE user_id=%s ORDER BY start_date", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        return
    cursor.execute("SELECT notification_timezone FROM users WHERE user_id=%s", (user_id,))
    tz = cursor.fetchone()["notification_timezone"]
    now = utc_now().astimezone(timezone.utc).replace(tzinfo=None)
    for row in rows:
        cursor.execute("SELECT start_date,end_date FROM cycle_revisions WHERE cycle_id=%s ORDER BY known_at DESC,revision_id DESC LIMIT 1", (row["cycle_id"],))
        previous = cursor.fetchone()
        if previous and (previous["start_date"], previous["end_date"]) == (row["start_date"], row["end_date"]):
            continue
        cursor.execute("INSERT INTO cycle_revisions (cycle_id,user_id,start_date,end_date,known_at,source,timezone_name) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       (row["cycle_id"], user_id, row["start_date"], row["end_date"], now, source, tz))


def mark_cycle_history_reset(cursor, user_id: int) -> None:
    cursor.execute("UPDATE users SET cycle_history_reset_at=%s,research_data_epoch=research_data_epoch+1 WHERE user_id=%s",
                   (utc_now().astimezone(timezone.utc).replace(tzinfo=None), user_id))
