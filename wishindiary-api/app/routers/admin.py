"""Research administration; permission is always enforced by the server."""
from fastapi import APIRouter, Depends

from app.core.audit import audit
from app.core.config import settings
from app.core.errors import AppError
from app.routers.auth import get_current_user_id
from app.services.research_service import ResearchService

router = APIRouter(prefix="/api/v1/admin", tags=["Research administration"])


def require_admin(user_id: int = Depends(get_current_user_id)) -> int:
    if user_id not in settings.admin_user_ids:
        raise AppError(403, "forbidden", "需要研究管理员权限")
    return user_id


@router.get("/research")
def research_summary(user_id: int = Depends(require_admin)):
    result = ResearchService().get_summary()
    audit("research.summary", actor_user_id=user_id, success=True)
    return result
