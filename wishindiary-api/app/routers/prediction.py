"""周期预测路由（薄层：仅做请求解析与响应返回）。"""

from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user_id
from app.schemas.prediction import PredictionResponse
from app.services.prediction_service import PredictionService

router = APIRouter(prefix="/api/v1", tags=["Prediction"])

# 复用离线预训练模型（应用启动时加载一次，请求时只做推理，不重训）
_prediction_service = PredictionService()


@router.get("/prediction", response_model=PredictionResponse)
def get_user_prediction(user_id: int = Depends(get_current_user_id)):
    return _prediction_service.get_prediction(user_id)
