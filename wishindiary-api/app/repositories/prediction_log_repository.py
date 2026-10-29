"""Forecast snapshots, selected by cycle and issuance time rather than outcome."""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def get_pending_prediction_for_reconcile(cursor, user_id: int, start_date: date):
    """Match the preceding cycle's first snapshot, issued before the actual day.

    DATE outcomes have no time of day. Conservatively exclude forecasts issued
    on that local day, including retrospective backfills and legacy logs.
    """
    cursor.execute("SELECT notification_timezone FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    if user is None:
        return None
    cutoff = datetime.combine(start_date, time.min, ZoneInfo(user["notification_timezone"]))
    cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    cursor.execute(
        """
        SELECT pred_id, predicted_date
        FROM prediction_logs
        WHERE user_id = %s AND actual_date IS NULL AND issued_at < %s
          AND anchor_start_date = (
            SELECT MAX(start_date) FROM cycles WHERE user_id = %s AND start_date < %s
          )
        LIMIT 1 FOR UPDATE
        """,
        (user_id, cutoff, user_id, start_date),
    )
    return cursor.fetchone()


def reconcile_prediction(cursor, pred_id: int, user_id: int, actual_date: date, error_days: int) -> None:
    cursor.execute(
        """
        UPDATE prediction_logs SET actual_date = %s, error_days = %s
        WHERE pred_id = %s AND user_id = %s AND actual_date IS NULL
        """,
        (actual_date, error_days, pred_id, user_id),
    )


def insert_prediction_snapshot(cursor, user_id: int, prediction: dict, *, method: str,
                               model_sha256: str | None = None) -> None:
    """Keep the first committed forecast for the current anchor, even after refresh.

    The user lock is shared with log_start; a forecast computed before a new
    cycle was recorded cannot attach itself to the old anchor afterward.
    """
    cursor.execute("SELECT user_id FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
    if cursor.fetchone() is None:
        return
    cursor.execute(
        "SELECT start_date FROM cycles WHERE user_id = %s ORDER BY start_date DESC LIMIT 1 FOR UPDATE",
        (user_id,),
    )
    latest = cursor.fetchone()
    anchor = date.fromisoformat(prediction["last_period_start"])
    if latest is None or latest["start_date"] != anchor:
        return
    interval = prediction.get("confidence_interval") or {}
    cursor.execute(
        """
        INSERT INTO prediction_logs
          (user_id, anchor_start_date, predicted_date, issued_at, prediction_method,
           model_version, model_sha256, interval_low, interval_high)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE pred_id = pred_id
        """,
        (user_id, anchor, prediction["next_period_start"],
         datetime.now(timezone.utc).replace(tzinfo=None), method, prediction["model_version"],
         model_sha256, interval.get("low"), interval.get("high")),
    )


# If the user edits/deletes/backfills a cycle, previously reconciled outcomes
# no longer necessarily match their current history. Only adjacent, existing
# anchor/outcome pairs belong in the displayed prospective error statistics.
VALID_SNAPSHOT_OUTCOME = """
    anchor_start_date IS NOT NULL AND issued_at IS NOT NULL AND actual_date IS NOT NULL
    AND EXISTS (SELECT 1 FROM cycles c WHERE c.user_id = prediction_logs.user_id
                AND c.start_date = prediction_logs.anchor_start_date)
    AND actual_date = (SELECT MIN(c.start_date) FROM cycles c
                      WHERE c.user_id = prediction_logs.user_id
                        AND c.start_date > prediction_logs.anchor_start_date)
"""
