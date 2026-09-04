import logging

from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user_id
from app.schemas.stats import StatsResponse
from app.services.stats_service import StatsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Dashboard & Stats"])

_stats_service = StatsService()


@router.get("/stats", response_model=StatsResponse)
def get_user_stats(user_id: int = Depends(get_current_user_id)):
    """获取当前登录用户的仪表盘周期与打卡数据（受 JWT 保护）"""
    return _stats_service.get_stats(user_id)
