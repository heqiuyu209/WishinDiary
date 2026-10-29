from fastapi import APIRouter, Depends

from app.routers.auth import get_current_user_id
from app.schemas.notifications import (
    EmailBindingRequest, EmailVerificationResponse, NotificationPreferences,
    NotificationSettingsResponse, VerifyEmailRequest,
)
from app.schemas.common import StatusResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/v1/notifications", tags=["Email and reminders"])
service = NotificationService()


@router.get("/settings", response_model=NotificationSettingsResponse)
def notification_settings(user_id: int = Depends(get_current_user_id)):
    return service.get_settings(user_id)


@router.post("/email/request", response_model=EmailVerificationResponse)
def request_email_verification(req: EmailBindingRequest, user_id: int = Depends(get_current_user_id)):
    return service.request_verification(user_id, str(req.email))


@router.post("/email/verify", response_model=StatusResponse)
def verify_email(req: VerifyEmailRequest, user_id: int = Depends(get_current_user_id)):
    return service.verify_email(user_id, req.code)


@router.delete("/email", response_model=StatusResponse)
def unbind_email(user_id: int = Depends(get_current_user_id)):
    return service.unbind_email(user_id)


@router.put("/settings", response_model=StatusResponse)
def update_notification_settings(req: NotificationPreferences, user_id: int = Depends(get_current_user_id)):
    return service.update_preferences(user_id, req)
