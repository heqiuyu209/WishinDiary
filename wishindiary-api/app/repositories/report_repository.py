"""Repository helpers for health report queries."""


def get_user_cycle_summary(cursor, user_id: int):
    cursor.execute("""
        SELECT COUNT(*) AS total_cycles, AVG(cycle_length) AS avg_cycle_length
        FROM cycles
        WHERE user_id = %s
          AND cycle_length IS NOT NULL
    """, (user_id,))
    return cursor.fetchone()
