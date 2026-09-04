"""每日健康日志数据访问层。"""

import json
from datetime import date


def _dump_symptom_levels(levels: dict | None) -> str:
    """symptom_levels 统一序列化为 JSON 字符串落库（服务端保证键全集与取值已校验）。"""
    return json.dumps(levels or {}, ensure_ascii=False)


def upsert_daily_log(
    cursor,
    user_id: int,
    *,
    log_date: date,
    mood_level: int,
    cramps_severity: int,
    is_exercise: bool,
    is_intercourse: bool,
    exercise_type: str | None,
    exercise_minutes: int,
    diet_tag: str | None,
    journal_text: str | None,
    sleep_duration_minutes: int = 0,
    sleep_quality: int = 0,
    is_late_night: bool = False,
    is_medication: bool = False,
    medication_note: str | None = None,
    symptom_levels: dict | None = None,
) -> None:
    """插入或更新用户某天的健康日志（按 (user_id, log_date) 幂等 upsert）。"""
    symptom_levels_json = _dump_symptom_levels(symptom_levels)
    cursor.execute(
        """
        INSERT INTO daily_logs
        (user_id, log_date, mood_level, cramps_severity, is_exercise, is_intercourse,
         exercise_type, exercise_minutes, diet_tag, journal_text,
         sleep_duration_minutes, sleep_quality, is_late_night, is_medication,
         medication_note, symptom_levels)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            mood_level = VALUES(mood_level),
            cramps_severity = VALUES(cramps_severity),
            is_exercise = VALUES(is_exercise),
            is_intercourse = VALUES(is_intercourse),
            exercise_type = VALUES(exercise_type),
            exercise_minutes = VALUES(exercise_minutes),
            diet_tag = VALUES(diet_tag),
            journal_text = VALUES(journal_text),
            sleep_duration_minutes = VALUES(sleep_duration_minutes),
            sleep_quality = VALUES(sleep_quality),
            is_late_night = VALUES(is_late_night),
            is_medication = VALUES(is_medication),
            medication_note = VALUES(medication_note),
            symptom_levels = VALUES(symptom_levels)
        """,
        (
            user_id, log_date, mood_level, cramps_severity,
            is_exercise, is_intercourse, exercise_type,
            exercise_minutes, diet_tag, journal_text,
            sleep_duration_minutes, sleep_quality,
            is_late_night, is_medication, medication_note,
            symptom_levels_json,
        ),
    )


def _normalize_row(row: dict) -> dict:
    """读取时把 MySQL 行归一化：JSON 文本列解析回 dict，TINYINT 布尔转 bool。"""
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
    return row


def get_daily_log_by_date(
    cursor,
    user_id: int,
    log_date: date,
) -> dict | None:
    """查询用户某一天的健康日志（含全部字段）；无记录返回 None。"""
    cursor.execute(
        """
        SELECT log_date, mood_level, cramps_severity, is_exercise, is_intercourse,
               exercise_type, exercise_minutes, diet_tag, journal_text,
               sleep_duration_minutes, sleep_quality, is_late_night, is_medication,
               medication_note, symptom_levels
        FROM daily_logs
        WHERE user_id = %s AND log_date = %s
        """,
        (user_id, log_date),
    )
    row = cursor.fetchone()
    return _normalize_row(row) if row else None


def delete_daily_log_by_date(cursor, user_id: int, log_date: date) -> int:
    """删除用户某一天的健康日志，返回影响行数（0=无记录）。"""
    cursor.execute(
        "DELETE FROM daily_logs WHERE user_id = %s AND log_date = %s",
        (user_id, log_date),
    )
    return cursor.rowcount
