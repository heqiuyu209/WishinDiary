"""Daily log business logic（每日健康日志 service 层）。"""

import logging
from datetime import date

from app.core.audit import audit
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
    """每日日志业务：保存日志并生成个性化 AI 健康与膳食营养建议。"""

    def save(self, user_id: int, req: DailyLogRequest) -> dict:
        if req.log_date > date.today():
            raise AppError(400, "invalid_input", "日志日期不能晚于今天")

        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
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
        """基于症状与日记生成个性化建议（纯函数，便于单元测试）。"""
        advices: list[str] = []
        if req.cramps_severity >= 2:
            advices.append(
                "检测到腹痛较为明显，建议多喝温开水，适当补充富含镁元素与维生素 B6 的食物（如香蕉、坚果、深色蔬菜）以缓解肌肉痉挛。"
            )
        if req.is_exercise and req.exercise_minutes > 45:
            advices.append(
                f"今日进行了 {req.exercise_minutes} 分钟的 {req.exercise_type or '运动'}，体力消耗较大，请注意及时补充电解质和优质蛋白质。"
            )
        if req.diet_tag and ("辛辣" in req.diet_tag or "油腻" in req.diet_tag):
            advices.append(
                "饮食偏向重口味，可能会加重盆腔充血或身体负担，建议多吃富含膳食纤维的果蔬促进代谢。"
            )
        if req.journal_text and any(k in req.journal_text for k in ["压力", "焦虑", "失眠", "累", "烦"]):
            advices.append(
                "日记中透露出一定的生活压力，建议睡前进行 10 分钟深呼吸放松或泡个温水脚，保证充足睡眠。"
            )
        if not advices:
            advices.append("今日身体状态平稳，继续保持规律作息和均衡饮食哦！")
        return advices
