import json


def get_recent_daily_logs(cursor, user_id: int, limit: int = 30):
    limit = max(1, min(int(limit), 100))
    cursor.execute("""
        SELECT
            log_date,
            mood_level,
            cramps_severity,
            is_exercise,
            exercise_type,
            journal_text,
            sleep_duration_minutes,
            sleep_quality,
            is_late_night,
            is_medication,
            medication_note,
            symptom_levels
        FROM daily_logs
        WHERE user_id = %s
        ORDER BY log_date DESC
        LIMIT %s
    """, (user_id, limit))
    rows = cursor.fetchall()
    for row in rows:
        raw = row.get("symptom_levels")
        if isinstance(raw, str):
            try:
                row["symptom_levels"] = json.loads(raw)
            except (ValueError, TypeError):
                row["symptom_levels"] = {}
        if not isinstance(row.get("symptom_levels"), dict):
            row["symptom_levels"] = {}
        if row.get("is_late_night") is not None:
            row["is_late_night"] = bool(row["is_late_night"])
        if row.get("is_medication") is not None:
            row["is_medication"] = bool(row["is_medication"])
    return rows


def get_user_dashboard_data(cursor, user_id: int, log_limit: int = 30):
    """Return the user's cycles and bounded recent logs."""
    cursor.execute("""
        SELECT c.cycle_id, c.start_date, c.end_date, c.cycle_length, c.bleeding_days,
          (SELECT kind FROM cycle_tracking_events e WHERE e.cycle_id=c.cycle_id
            AND e.anchor_start_date=c.start_date ORDER BY e.known_at DESC,e.event_id DESC LIMIT 1) AS tracking_kind,
          (SELECT as_of_date FROM cycle_tracking_events e WHERE e.cycle_id=c.cycle_id
            AND e.anchor_start_date=c.start_date ORDER BY e.known_at DESC,e.event_id DESC LIMIT 1) AS tracking_as_of_date
        FROM cycles c
        WHERE c.user_id = %s
        ORDER BY c.start_date ASC
    """, (user_id,))
    cycles = cursor.fetchall()
    return cycles, get_recent_daily_logs(cursor, user_id, log_limit)
