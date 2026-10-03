"""Daily logs and their timestamped, structured research revisions."""
import json
from datetime import date, timezone

from app.core.calendar_time import utc_now

DAILY_FIELDS = (
    "mood_level", "cramps_severity", "is_exercise", "is_intercourse", "exercise_type",
    "exercise_minutes", "diet_tag", "journal_text", "sleep_duration_minutes", "sleep_quality",
    "is_late_night", "is_medication", "medication_note", "symptom_levels", "stress_level",
    "exercise_intensity", "sleep_start_minutes", "is_night_shift",
)
RESEARCH_FIELDS = (
    "sleep_duration_minutes", "sleep_quality", "sleep_start_minutes", "is_late_night", "is_night_shift",
    "stress_level", "is_exercise", "exercise_minutes", "exercise_intensity", "is_medication",
)


def upsert_daily_log(cursor, user_id: int, *, log_date: date, **fields) -> None:
    """Caller holds the user lock. Current row and revision commit together."""
    values = {name: fields.get(name) for name in DAILY_FIELDS}
    values["symptom_levels"] = json.dumps(fields.get("symptom_levels") or {}, ensure_ascii=False)
    now = utc_now().astimezone(timezone.utc).replace(tzinfo=None)
    columns = ("user_id", "log_date", *DAILY_FIELDS, "recorded_at", "updated_at", "recording_version")
    updates = ', '.join(f'{name}=VALUES({name})' for name in (*DAILY_FIELDS, "updated_at", "recording_version"))
    cursor.execute(
        f"INSERT INTO daily_logs ({','.join(columns)}) VALUES ({','.join(['%s'] * len(columns))}) "
        f"ON DUPLICATE KEY UPDATE {updates}, recorded_at=COALESCE(recorded_at,VALUES(recorded_at))",
        (user_id, log_date, *values.values(), now, now, 1),
    )
    cursor.execute("SELECT d.log_id,u.notification_timezone FROM daily_logs d JOIN users u ON u.user_id=d.user_id "
                   "WHERE d.user_id=%s AND d.log_date=%s", (user_id, log_date))
    row = cursor.fetchone()
    payload = json.dumps({name: fields.get(name) for name in RESEARCH_FIELDS}, ensure_ascii=False)
    cursor.execute("INSERT INTO daily_log_revisions (log_id,user_id,log_date,known_at,timezone_name,source,payload) "
                   "VALUES (%s,%s,%s,%s,%s,'user_recorded',%s)",
                   (row["log_id"], user_id, log_date, now, row["notification_timezone"], payload))


def _normalize_row(row: dict) -> dict:
    raw = row.get("symptom_levels")
    if isinstance(raw, str):
        row["symptom_levels"] = json.loads(raw)
    for name in ("is_exercise", "is_intercourse", "is_late_night", "is_night_shift", "is_medication"):
        if row.get(name) is not None:
            row[name] = bool(row[name])
    for name in ("recorded_at", "updated_at"):
        if row.get(name) is not None:
            row[name] = row[name].replace(tzinfo=timezone.utc).isoformat()
    return row


def get_daily_log_by_date(cursor, user_id: int, log_date: date) -> dict | None:
    cursor.execute(f"SELECT log_date,{','.join(DAILY_FIELDS)},recording_version,recorded_at,updated_at "
                   "FROM daily_logs WHERE user_id=%s AND log_date=%s", (user_id, log_date))
    row = cursor.fetchone()
    return _normalize_row(row) if row else None


def delete_daily_log_by_date(cursor, user_id: int, log_date: date) -> int:
    # Revision FK cascades; deleted health information must not survive in history.
    cursor.execute("DELETE FROM daily_logs WHERE user_id=%s AND log_date=%s", (user_id, log_date))
    return cursor.rowcount


def get_daily_revisions_as_of(cursor, user_id: int, as_of):
    if as_of.tzinfo is None:
        raise ValueError("Feature cutoff must be timezone-aware")
    cursor.execute("SELECT revision_id,user_id,log_date,known_at,timezone_name,source,payload "
                   "FROM daily_log_revisions WHERE user_id=%s AND known_at < %s ORDER BY known_at,revision_id",
                   (user_id, as_of.astimezone(timezone.utc).replace(tzinfo=None)))
    return list(cursor.fetchall())
