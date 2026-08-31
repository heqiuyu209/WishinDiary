"""Cycle data access helpers."""


def get_user_valid_cycles(cursor, user_id: int):
    cursor.execute("""
        SELECT start_date, cycle_length, bleeding_days
        FROM cycles
        WHERE user_id = %s AND cycle_length IS NOT NULL
        ORDER BY start_date ASC
    """, (user_id,))
    return cursor.fetchall()


def get_user_latest_cycle(cursor, user_id: int):
    cursor.execute("""
        SELECT start_date, bleeding_days
        FROM cycles
        WHERE user_id = %s
        ORDER BY start_date DESC LIMIT 1
    """, (user_id,))
    return cursor.fetchone()


def get_user_daily_logs(cursor, user_id: int):
    cursor.execute("""
        SELECT log_date, mood_level, cramps_severity, is_exercise, is_intercourse
        FROM daily_logs WHERE user_id = %s
    """, (user_id,))
    return cursor.fetchall()


def get_cycle_by_id(cursor, user_id: int, cycle_id: int):
    """按 id 获取周期，并校验归属用户。"""
    cursor.execute("""
        SELECT cycle_id, user_id, start_date, end_date, cycle_length, bleeding_days
        FROM cycles
        WHERE cycle_id = %s AND user_id = %s
    """, (cycle_id, user_id))
    return cursor.fetchone()


def get_all_cycles_sorted(cursor, user_id: int):
    """获取用户全部周期（按开始日期升序）。"""
    cursor.execute("""
        SELECT cycle_id, start_date, end_date, cycle_length, bleeding_days
        FROM cycles
        WHERE user_id = %s
        ORDER BY start_date ASC
    """, (user_id,))
    return cursor.fetchall()


def update_cycle_dates(cursor, cycle_id: int, start_date, end_date, bleeding_days):
    """更新指定周期的日期字段。

    end_date 为 None 时表示取消闭合（同时清空 bleeding_days / cycle_length）。
    """
    if end_date is None:
        cursor.execute("""
            UPDATE cycles SET start_date = %s, end_date = NULL,
                              bleeding_days = NULL, cycle_length = NULL
            WHERE cycle_id = %s
        """, (start_date, cycle_id))
    else:
        cursor.execute("""
            UPDATE cycles SET start_date = %s, end_date = %s, bleeding_days = %s
            WHERE cycle_id = %s
        """, (start_date, end_date, bleeding_days, cycle_id))


def delete_cycle(cursor, cycle_id: int):
    """删除指定周期。"""
    cursor.execute("DELETE FROM cycles WHERE cycle_id = %s", (cycle_id,))


def recalculate_cycle_lengths(cursor, user_id: int):
    """重算用户所有已闭合周期的周期长度。

    规则：cycle_length = 下一个周期.start_date - 本周期.start_date
    最后一个周期若未闭合，其 cycle_length 置为 NULL。
    """
    cycles = get_all_cycles_sorted(cursor, user_id)

    for idx, cycle in enumerate(cycles):
        if idx + 1 < len(cycles):
            next_start = cycles[idx + 1]['start_date']
            this_start = cycle['start_date']
            cycle_length = (next_start - this_start).days
            cursor.execute("""
                UPDATE cycles SET cycle_length = %s WHERE cycle_id = %s
            """, (cycle_length, cycle['cycle_id']))
        else:
            # 最后一个周期没有后继，无法推导周期长度。即使它已闭合，
            # 也必须清掉旧值，避免删除后继周期后留下过期统计。
            cursor.execute("""
                UPDATE cycles SET cycle_length = NULL WHERE cycle_id = %s
            """, (cycle['cycle_id'],))
