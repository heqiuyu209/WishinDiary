import logging

from fastapi import APIRouter, HTTPException, Depends, status

from app.core.database import get_db_connection
from app.routers.auth import get_current_user_id
from app.repositories import get_user_dashboard_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Dashboard & Stats"])

@router.get("/stats")
def get_user_stats(user_id: int = Depends(get_current_user_id)):
    """获取当前登录用户的仪表盘周期与打卡数据（受 JWT 保护）"""
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cycles, logs = get_user_dashboard_data(cursor, user_id)

        return {
            "status": "success",
            "cycles": cycles,
            "recent_logs": logs
        }
    except Exception:
        logger.exception("Stats loading failed for user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="统计数据加载失败，请稍后重试"
        )
    finally:
        if connection is not None:
            connection.close()
