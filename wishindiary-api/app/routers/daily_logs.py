"""每日健康日志路由（薄层：仅做请求解析与响应返回）。"""

from datetime import date

from fastapi import APIRouter, Depends, Request

from app.core.audit import audit
from app.routers.auth import get_current_user_id
from app.schemas.daily_log import (
    DailyLogReadResponse,
    DailyLogRequest,
    DailyLogResponse,
    DailyLogUpdateRequest,
)
from app.services.daily_log_service import DailyLogService

router = APIRouter(prefix="/api/v1", tags=["Daily Log"])

_daily_log_service = DailyLogService()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/daily_log", response_model=DailyLogResponse)
def save_daily_log(
    req: DailyLogRequest,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """保存每日健康日志，并基于症状与日记由 AI 生成个性化健康与膳食营养建议。"""
    result = _daily_log_service.save(user_id, req)
    audit(
        "daily_log.save",
        actor_user_id=user_id,
        ip=_client_ip(request),
        success=True,
        details={"log_date": str(getattr(req, "log_date", ""))},
    )
    return result


@router.get("/daily_log", response_model=DailyLogReadResponse)
def get_daily_log(
    date: date,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """按日期查询单日健康日志；无记录返回 404。"""
    result = _daily_log_service.get_by_date(user_id, date)
    audit(
        "daily_log.get",
        actor_user_id=user_id,
        ip=_client_ip(request),
        success=True,
        details={"log_date": str(date)},
    )
    return {"status": "success", "log": result}


@router.put("/daily_log", response_model=DailyLogResponse)
def update_daily_log(
    req: DailyLogUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """幂等覆盖某天日志（语义同 POST，允许修改），并重新生成 AI 建议。"""
    result = _daily_log_service.update(user_id, req)
    audit(
        "daily_log.update",
        actor_user_id=user_id,
        ip=_client_ip(request),
        success=True,
        details={"log_date": str(getattr(req, "log_date", ""))},
    )
    return result


@router.delete("/daily_log", response_model=DailyLogResponse)
def delete_daily_log(
    date: date,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """删除单日健康日志；无记录返回 404。"""
    _daily_log_service.delete(user_id, date)
    audit(
        "daily_log.delete",
        actor_user_id=user_id,
        ip=_client_ip(request),
        success=True,
        details={"log_date": str(date)},
    )
    return {"status": "success", "message": "健康日志已删除", "ai_health_advice": []}
