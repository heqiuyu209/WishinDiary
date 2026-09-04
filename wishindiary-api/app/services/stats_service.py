"""Dashboard stats business logic（仪表盘统计 service 层）。"""

import logging

from app.core.database import transaction
from app.core.errors import AppError
from app.repositories.stats_repository import get_user_dashboard_data

logger = logging.getLogger(__name__)


class StatsService:
    """仪表盘数据业务：查询周期与最近打卡记录。"""

    def get_stats(self, user_id: int) -> dict:
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cycles, logs = get_user_dashboard_data(cursor, user_id)
            return {"status": "success", "cycles": cycles, "recent_logs": logs}
        except AppError:
            raise
        except Exception:
            logger.exception("Stats loading failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "统计数据加载失败，请稍后重试")
