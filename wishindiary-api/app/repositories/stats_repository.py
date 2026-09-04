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
        if "is_late_night" in row:
            row["is_late_night"] = bool(row["is_late_night"])
        if "is_medication" in row:
            row["is_medication"] = bool(row["is_medication"])
    return rows


def get_user_dashboard_data(cursor, user_id: int, log_limit: int = 30):
    """Return the user's cycles and bounded recent logs."""
    cursor.execute("""
        SELECT cycle_id, start_date, end_date, cycle_length, bleeding_days
        FROM cycles
        WHERE user_id = %s
        ORDER BY start_date ASC
    """, (user_id,))
    cycles = cursor.fetchall()
    return cycles, get_recent_daily_logs(cursor, user_id, log_limit)
