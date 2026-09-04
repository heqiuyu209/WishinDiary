"""周期写入路由（薄层：仅做请求解析与响应返回）。

业务规则与事务管理已下沉到 app.services.cycle_service.CycleService，
数据访问在 app.repositories.cycle_repository，本文件只负责 HTTP 契约。
"""

import logging

from fastapi import APIRouter, Depends, Request

from app.core.audit import audit
from app.routers.auth import get_current_user_id
from app.schemas.cycle import (
    CycleOperationResponse,
    CycleUpdateRequest,
    LogEndRequest,
    LogStartRequest,
)
from app.services import CycleService
from app.services.cycle_service import _UNSET

router = APIRouter(prefix="/api/v1", tags=["Cycles"])
logger = logging.getLogger(__name__)

_cycle_service = CycleService()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _audit_cycle(action: str, user_id: int, ip: str | None, result) -> None:
    audit(
        action,
        actor_user_id=user_id,
        ip=ip,
        success=True,
        details={"cycle_id": getattr(result, "cycle_id", None)},
    )


@router.post("/log_start", response_model=CycleOperationResponse)
def log_start(
    req: LogStartRequest,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """标记周期开始，并自动闭合上一未结束周期、回填预测对账。"""
    result = _cycle_service.log_start(user_id, req.start_date)
    _audit_cycle("cycle.log_start", user_id, _client_ip(request), result)
    return result


@router.post("/log_end", response_model=CycleOperationResponse)
def log_end(
    req: LogEndRequest,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """标记经期结束（或调整区间结束日）。"""
    result = _cycle_service.log_end(user_id, req.end_date, req.cycle_id)
    _audit_cycle("cycle.log_end", user_id, _client_ip(request), result)
    return result


@router.put("/cycles/{cycle_id}", response_model=CycleOperationResponse)
def update_cycle(
    cycle_id: int,
    req: CycleUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """编辑一个已存在的周期（修正开始/结束日期）。

    start_date/end_date 均通过 model_fields_set 判断是否显式传入；
    end_date 显式传 null 表示取消闭合该周期。
    """
    start_date = req.start_date if "start_date" in req.model_fields_set else _UNSET
    end_date = req.end_date if "end_date" in req.model_fields_set else _UNSET
    result = _cycle_service.update_cycle(user_id, cycle_id, start_date, end_date)
    _audit_cycle("cycle.update", user_id, _client_ip(request), result)
    return result


@router.delete("/cycles/{cycle_id}", response_model=CycleOperationResponse)
def delete_cycle_endpoint(
    cycle_id: int,
    user_id: int = Depends(get_current_user_id),
    request: Request = None,
):
    """删除一个误操作的周期。"""
    result = _cycle_service.delete_cycle(user_id, cycle_id)
    _audit_cycle("cycle.delete", user_id, _client_ip(request), result)
    return result
