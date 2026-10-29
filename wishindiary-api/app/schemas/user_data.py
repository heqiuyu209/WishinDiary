"""用户数据导出响应模型。"""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import StatusResponse


class UserProfile(BaseModel):
    user_id: int
    username: str
    created_at: str | None = None
    cycle_history_reset_at: str | None = None


class ExportUserDataResponse(StatusResponse):
    """统一 /user/export 响应结构。"""

    exported_at: str = Field(..., description="导出时间（UTC ISO 格式）")
    user: UserProfile
    cycles: list[dict[str, Any]] = Field(default_factory=list)
    research_consent_events: list[dict[str, Any]] = Field(default_factory=list)
    research_background_revisions: list[dict[str, Any]] = Field(default_factory=list)
    cycle_revisions: list[dict[str, Any]] = Field(default_factory=list)
    cycle_tracking_events: list[dict[str, Any]] = Field(default_factory=list)
    daily_logs: list[dict[str, Any]] = Field(default_factory=list)
    daily_log_revisions: list[dict[str, Any]] = Field(default_factory=list)
    prediction_logs: list[dict[str, Any]] = Field(default_factory=list)


class DeleteUserDataResponse(StatusResponse):
    """统一 DELETE /user/me 响应结构。"""

    pass
