def get_recent_daily_logs(cursor, user_id: int, limit: int = 30):
    limit = max(1, min(int(limit), 100))
    cursor.execute("""
        SELECT
            log_date,
            mood_level,
            cramps_severity,
            is_exercise,
            exercise_type,
            journal_text
        FROM daily_logs
        WHERE user_id = %s
        ORDER BY log_date DESC
        LIMIT %s
    """, (user_id, limit))
    return cursor.fetchall()


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
