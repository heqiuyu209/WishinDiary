"""预测对账日志（prediction_logs）数据访问层。

负责预测待对账记录的查询、写入与回填，供周期写入与预测推理两条链路复用。
"""

from datetime import date


def get_pending_prediction_for_reconcile(cursor, user_id: int, start_date: date):
    """取最近一条尚未对账的预测记录（行级排他锁，供 log_start 回填）。

    排序策略：按预测日期与实际日期的绝对差值最近优先，created_at 兜底。
    无待对账记录时返回 None（不插入残缺记录）。
    """
    cursor.execute(
        """
        SELECT pred_id, predicted_date
        FROM prediction_logs
        WHERE user_id = %s AND actual_date IS NULL
        ORDER BY ABS(DATEDIFF(predicted_date, %s)), created_at ASC
        LIMIT 1
        FOR UPDATE
        """,
        (user_id, start_date),
    )
    return cursor.fetchone()


def reconcile_prediction(
    cursor,
    pred_id: int,
    user_id: int,
    actual_date: date,
    error_days: int,
) -> None:
    """回填一条预测记录的实际日期与误差天数。"""
    cursor.execute(
        """
        UPDATE prediction_logs
        SET actual_date = %s, error_days = %s
        WHERE pred_id = %s AND user_id = %s
        """,
        (actual_date, error_days, pred_id, user_id),
    )


def get_existing_pending_prediction(cursor, user_id: int, predicted_date: date):
    """查询是否已存在同预测日期且未对账的记录（避免重复插入）。"""
    cursor.execute(
        """
        SELECT pred_id FROM prediction_logs
        WHERE user_id = %s AND predicted_date = %s AND actual_date IS NULL
        LIMIT 1
        """,
        (user_id, predicted_date),
    )
    return cursor.fetchone()


def insert_pending_prediction(cursor, user_id: int, predicted_date: date) -> None:
    """插入一条待对账的预测记录。"""
    cursor.execute(
        "INSERT INTO prediction_logs (user_id, predicted_date) VALUES (%s, %s)",
        (user_id, predicted_date),
    )
