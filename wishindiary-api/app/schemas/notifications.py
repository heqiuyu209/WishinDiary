from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError
from app.schemas.common import StatusResponse


class EmailBindingRequest(BaseModel):
    email: EmailStr = Field(max_length=254)


class VerifyEmailRequest(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class NotificationPreferences(BaseModel):
    enabled: bool
    lead_days: Literal[1, 2, 3] = 2
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise PydanticCustomError("invalid_timezone", "请选择有效时区")
        return value


class NotificationSettingsResponse(StatusResponse):
    email: str | None
    email_verified: bool
    pending_email: str | None
    enabled: bool
    lead_days: int
    timezone: str
    mail_available: bool
    last_delivery_state: str | None


class EmailVerificationResponse(StatusResponse):
    resend_after_seconds: int = 60
