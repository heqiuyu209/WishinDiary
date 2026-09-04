"""Cycle data access helpers."""


def get_user_valid_cycles(cursor, user_id: int):
    cursor.execute("""
        SELECT start_date, cycle_length, bleeding_days
        FROM cycles
        WHERE user_id = %s AND cycle_length IS NOT NULL
        ORDER BY start_date ASC
    """, (user_id,))
    return cursor.fetchall()


def get_unclosed_cycle_for_update(cursor, user_id: int):
    """取最近一条未结束的周期并加行级排他锁（供 log_start 使用）。"""
    cursor.execute("""
        SELECT cycle_id, start_date
        FROM cycles
        WHERE user_id = %s
          AND end_date IS NULL
        ORDER BY start_date DESC
        LIMIT 1
            FOR UPDATE
    """, (user_id,))
    return cursor.fetchone()


def close_cycle(cursor, cycle_id: int, end_date, cycle_length: int, bleeding_days: int):
    """闭合指定周期（写入结束日期、周期长度与流血天数）。"""
    cursor.execute("""
        UPDATE cycles
        SET end_date      = %s,
            cycle_length  = %s,
            bleeding_days = %s
        WHERE cycle_id = %s
    """, (end_date, cycle_length, bleeding_days, cycle_id))


def get_conflicting_closed_cycle(cursor, user_id: int, start_date):
    """查询是否已有已闭合周期覆盖该开始日期。

    用于 log_start 重叠校验：拒绝把新周期开始日建在一条已结束
    经期记录的区间内（例如已闭合 A[6-1, 6-28]，又提交 B[6-10]）。
    end_date 为 NULL 的未闭合周期不参与——它将在本流程内被闭合，
    若提前把它的开始日算作"s"命中反而会造成误判。
    """
    cursor.execute("""
        SELECT cycle_id, start_date, end_date
        FROM cycles
        WHERE user_id = %s
          AND end_date IS NOT NULL
          AND start_date <= %s
          AND end_date >= %s
        ORDER BY start_date ASC
        LIMIT 1
    """, (user_id, start_date, start_date))
    return cursor.fetchone()


def insert_cycle(cursor, user_id: int, start_date):
    """写入新周期，利用 UNIQUE KEY uk_user_start 兜底幂等性。"""
    cursor.execute("""
        INSERT INTO cycles (user_id, start_date)
        VALUES (%s, %s) ON DUPLICATE KEY
        UPDATE start_date =
        VALUES (start_date)
    """, (user_id, start_date))


def get_cycle_for_log_end(cursor, user_id: int, cycle_id: int | None = None):
    """定位 log_end 的目标周期。

    1. 指定 cycle_id 时精确定位该周期（用于修正历史周期）；
    2. 未指定时优先取最新未结束周期，其次回退到最新周期。
    """
    if cycle_id is not None:
        cursor.execute("""
            SELECT cycle_id, start_date FROM cycles
            WHERE cycle_id = %s AND user_id = %s
        """, (cycle_id, user_id))
        return cursor.fetchone()

    # 优先：最新未结束周期
    cursor.execute("""
        SELECT cycle_id, start_date FROM cycles
        WHERE user_id = %s AND end_date IS NULL
        ORDER BY start_date DESC LIMIT 1
    """, (user_id,))
    active_cycle = cursor.fetchone()
    if active_cycle:
        return active_cycle

    # 回退：最新周期（允许修正已自动闭合的结束日）
    cursor.execute("""
        SELECT cycle_id, start_date FROM cycles
        WHERE user_id = %s
        ORDER BY start_date DESC LIMIT 1
    """, (user_id,))
    return cursor.fetchone()


def get_prev_cycle(cursor, user_id: int, exclude_cycle_id: int, ref_date):
    """取指定日期之前的最近一个周期（排除自身，用于重叠校验）。"""
    cursor.execute("""
        SELECT cycle_id, start_date, end_date FROM cycles
        WHERE user_id = %s AND cycle_id <> %s AND start_date < %s
        ORDER BY start_date DESC LIMIT 1
    """, (user_id, exclude_cycle_id, ref_date))
    return cursor.fetchone()


def get_next_cycle(cursor, user_id: int, exclude_cycle_id: int, ref_date):
    """取指定日期之后的最近一个周期（排除自身，用于重叠校验）。"""
    cursor.execute("""
        SELECT cycle_id, start_date FROM cycles
        WHERE user_id = %s AND cycle_id <> %s AND start_date > %s
        ORDER BY start_date ASC LIMIT 1
    """, (user_id, exclude_cycle_id, ref_date))
    return cursor.fetchone()


def update_cycle_end(cursor, cycle_id: int, end_date, bleeding_days: int):
    """更新指定周期的结束日期与流血天数。"""
    cursor.execute("""
        UPDATE cycles SET end_date = %s, bleeding_days = %s WHERE cycle_id = %s
    """, (end_date, bleeding_days, cycle_id))


def get_user_latest_cycle(cursor, user_id: int):
    cursor.execute("""
        SELECT start_date, bleeding_days
        FROM cycles
        WHERE user_id = %s
        ORDER BY start_date DESC LIMIT 1
    """, (user_id,))
    return cursor.fetchone()


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
