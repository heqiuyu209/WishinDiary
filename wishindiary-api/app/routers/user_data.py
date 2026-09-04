"""用户健康数据的导出与删除接口（薄路由，逻辑下沉至 UserDataService）。

设计目标：
1. 数据导出：返回当前登录用户全部健康数据（个人资料、周期、每日日志、预测记录），
   便于用户行使数据可携带权 / 留存备份。
2. 数据删除：删除当前用户账号及其全部关联数据（级联清理），
   便于用户行使数据被遗忘权。
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.core.audit import audit
from app.routers.auth import get_current_user_id
from app.schemas.user_data import DeleteUserDataResponse, ExportUserDataResponse
from app.services.user_data_service import UserDataService

router = APIRouter(prefix="/api/v1/user", tags=["User Data"])
logger = logging.getLogger(__name__)

_user_data_service = UserDataService()


@router.get("/export", response_model=ExportUserDataResponse)
def export_user_data(
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """导出当前用户的全部健康数据（JSON）。"""
    result = _user_data_service.export_user_data(user_id)
    # 数据导出属于敏感操作：记录读取足迹，便于用户追查数据流向
    audit(
        "user_data.export",
        actor_user_id=user_id,
        ip=request.client.host if request.client else None,
        success=True,
    )
    return result


@router.delete("/me", response_model=DeleteUserDataResponse)
def delete_user_data(
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """删除当前用户账号及其全部关联数据（级联清理）。"""
    result = _user_data_service.delete_user_data(user_id)
    audit(
        "user_data.delete",
        actor_user_id=user_id,
        ip=request.client.host if request.client else None,
        success=True,
    )
    return result

