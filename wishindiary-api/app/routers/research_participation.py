from fastapi import APIRouter, Depends

from app.core.audit import audit
from app.routers.auth import get_current_user_id
from app.schemas.research_participation import ParticipationRequest, ResearchBackground
from app.services.research_participation_service import ResearchParticipationService

router = APIRouter(prefix="/api/v1/research", tags=["Voluntary research participation"])


@router.get("/participation")
def get_participation(user_id: int = Depends(get_current_user_id)):
    return ResearchParticipationService().get(user_id)


@router.put("/participation")
def decide_participation(req: ParticipationRequest, user_id: int = Depends(get_current_user_id)):
    result = ResearchParticipationService().decide(user_id, req)
    audit("research.join" if req.participate else "research.withdraw", actor_user_id=user_id)
    return result


@router.put("/background")
def save_background(req: ResearchBackground, user_id: int = Depends(get_current_user_id)):
    result = ResearchParticipationService().save_background(user_id, req)
    audit("research.background", actor_user_id=user_id)
    return result

