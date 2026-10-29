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
                    cursor.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                    if req.log_date > user_today(cursor, user_id):
                        raise AppError(400, "invalid_input", "日志日期不能晚于今天")
                    payload = req.model_dump()
                    payload["symptom_levels"] = req.symptom_levels or dict(DEFAULT_SYMPTOM_LEVELS)
                    upsert_daily_log(cursor, user_id, **payload)

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
                    cursor.execute("SELECT user_id FROM users WHERE user_id=%s FOR UPDATE", (user_id,))
                    if not cursor.fetchone():
                        raise AppError(404, "not_found", "账号不存在")
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
        if (req.stress_level or 0) >= 2:
            advices.append("已记录较明显的压力。可继续观察压力、作息与症状的变化，按需要寻求支持；此自评不是诊断。")
        if req.journal_text and any(k in req.journal_text for k in ["压力", "焦虑", "失眠", "累", "烦"]):
            advices.append("日记中提到了压力或睡眠困扰，可继续记录变化并安排休息；文字关键词不能确定压力程度或病因。")
        if not advices:
            advices.append("本次记录已保存。未填写的信息不能用于判断身体状态；请按实际情况继续记录。")
        return advices
