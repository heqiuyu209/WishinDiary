"""Daily log business logic（每日健康日志 service 层）。"""

import logging
from datetime import date

from app.core.audit import audit
from app.core.calendar_time import user_today
from app.core.database import transaction
from app.core.errors import AppError
from app.repositories.daily_log_repository import (
    delete_daily_log_by_date,
    get_daily_log_by_date,
    upsert_daily_log,
)
from app.schemas.daily_log import (
    DEFAULT_SYMPTOM_LEVELS,
    DailyLogRequest,
    DailyLogUpdateRequest,
)

logger = logging.getLogger(__name__)


class DailyLogService:
    """每日日志业务：保存日志并生成基于记录的提示。"""

    def save(self, user_id: int, req: DailyLogRequest) -> dict:
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    if req.log_date > user_today(cursor, user_id):
                        raise AppError(400, "invalid_input", "日志日期不能晚于今天")
                    upsert_daily_log(
                        cursor,
                        user_id,
                        log_date=req.log_date,
                        mood_level=req.mood_level,
                        cramps_severity=req.cramps_severity,
                        is_exercise=req.is_exercise,
                        is_intercourse=req.is_intercourse,
                        exercise_type=req.exercise_type,
                        exercise_minutes=req.exercise_minutes,
                        diet_tag=req.diet_tag,
                        journal_text=req.journal_text,
                        sleep_duration_minutes=req.sleep_duration_minutes,
                        sleep_quality=req.sleep_quality,
                        is_late_night=req.is_late_night,
                        is_medication=req.is_medication,
                        medication_note=req.medication_note,
                        # Pydantic v2 默认不校验 None 默认值，此处兜底为全 0 默认对象
                        symptom_levels=req.symptom_levels or dict(DEFAULT_SYMPTOM_LEVELS),
                    )

            audit(
                "daily_log.save",
                actor_user_id=user_id,
                success=True,
                details={"log_date": req.log_date.isoformat()},
            )

            advices = self._generate_advice(req)
            return {
                "status": "success",
                "message": "✨ 健康日志保存成功！",
                "ai_health_advice": advices,
                "advice_source": "rule_based",
            }
        except AppError:
            raise
        except Exception:
            logger.exception("save_daily_log failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "保存健康日志失败，请稍后重试")

    def update(self, user_id: int, req: DailyLogUpdateRequest) -> dict:
        """整体覆盖某天日志（幂等 upsert），语义同 POST，返回带 AI 建议。"""
        return self.save(user_id, req)

    def get_by_date(self, user_id: int, log_date: date) -> dict:
        """查询用户某天日志，不存在时抛出 404。"""
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    row = get_daily_log_by_date(cursor, user_id, log_date)
        except AppError:
            raise
        except Exception:
            logger.exception("get_daily_log failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "读取健康日志失败，请稍后重试")

        if not row:
            raise AppError(404, "not_found", "该日期尚无健康日志记录")
        return row

    def delete(self, user_id: int, log_date: date) -> None:
        """删除用户某天日志；无记录时抛出 404。"""
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    affected = delete_daily_log_by_date(cursor, user_id, log_date)
        except AppError:
            raise
        except Exception:
            logger.exception("delete_daily_log failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "删除健康日志失败，请稍后重试")

        if not affected:
            raise AppError(404, "not_found", "该日期尚无健康日志记录")

    @staticmethod
    def _generate_advice(req: DailyLogRequest) -> list[str]:
        """Transparent record-based hints, not clinical or AI assessment."""
        advices: list[str] = []
        names = {"headache": "头痛", "bloat": "腹胀", "breast_tenderness": "乳房胀痛", "fatigue": "疲劳"}
        reported = dict(req.symptom_levels or {})
        reported["cramps"] = req.cramps_severity
        names["cramps"] = "腹痛"
        significant = [names[key] for key, value in reported.items() if (value or 0) >= 2]
        if significant:
            advices.append("已记录较明显的" + "、".join(significant) + "。请记录出现时间、持续情况和是否影响生活；如持续、加重或影响日常活动，请联系专业医务人员。")
        if req.is_exercise and (req.exercise_minutes or 0) > 45:
            advices.append(f"已记录 {req.exercise_minutes} 分钟运动。按身体感受安排休息与饮水，避免勉强继续运动。")
        if req.journal_text and any(k in req.journal_text for k in ["压力", "焦虑", "失眠", "累", "烦"]):
            advices.append("日记中提到了压力或睡眠困扰，可继续记录变化并安排休息；文字关键词不能确定压力程度或病因。")
        if not advices:
            advices.append("本次记录已保存。未填写的信息不能用于判断身体状态；请按实际情况继续记录。")
        return advices
