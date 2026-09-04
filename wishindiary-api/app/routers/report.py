# app/routers/report.py
import logging

from fastapi import APIRouter, Depends
from app.routers.auth import get_current_user_id
from app.schemas.report import ReportResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1", tags=["Report"])
logger = logging.getLogger(__name__)

_report_service = ReportService()


@router.get("/report", response_model=ReportResponse)
def get_health_report(user_id: int = Depends(get_current_user_id)):
    """生成健康报告：周期统计、预测准确度与痛经评估。"""
    return _report_service.get_report(user_id)
