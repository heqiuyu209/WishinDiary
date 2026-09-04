"""认证接口的响应模型。"""

from pydantic import BaseModel, Field

from app.schemas.common import StatusResponse


class UserAuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class RegisterRequest(UserAuthRequest):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(UserAuthRequest):
    # Keep legacy accounts usable; new registrations still require 8+ characters.
    password: str = Field(min_length=1, max_length=128)


class RegisterResponse(StatusResponse):
    user_id: int | None = None


class LoginResponse(StatusResponse):
    user_id: int | None = None
    username: str | None = None


class SessionResponse(StatusResponse):
    user_id: int | None = None
    username: str | None = None
