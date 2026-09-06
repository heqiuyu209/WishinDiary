"""认证接口的响应模型。"""

from datetime import date

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.schemas.common import StatusResponse

# 相邻经期开始日期的医学合理间隔（宽松口径，与补录验证一致）
_PERIOD_MIN_GAP_DAYS = 15
_PERIOD_MAX_GAP_DAYS = 60


class UserAuthRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class RegisterRequest(UserAuthRequest):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    period_start_dates: list[date] = Field(
        default_factory=list,
        max_length=4,
        description=(
            "可选：新用户注册时补录最近 3~4 次经期开始日期（升序、不重复、"
            f"相邻间隔 {_PERIOD_MIN_GAP_DAYS}~{_PERIOD_MAX_GAP_DAYS} 天、不得晚于今天）。"
            "提供 2 个及以上即可构成至少 1 个完整周期，使新用户立即获得基础统计量与预测区间。"
        ),
    )

    @field_validator("period_start_dates")
    @classmethod
    def _validate_period_start_dates(cls, value: list[date]) -> list[date]:
        """补录经期日期的健壮校验：禁未来 / 去重 / 至少 2 个 / 相邻间隔 15~60 天。

        返回升序去重后的日期列表（供注册流程按时间顺序写入 cycles）。
        """
        if not value:
            return value

        today = date.today()
        for d in value:
            if d > today:
                raise PydanticCustomError(
                    "period_date_in_future", "补录经期开始日期不能晚于今天"
                )

        deduped = sorted(set(value))
        if len(deduped) != len(value):
            raise PydanticCustomError("period_date_duplicate", "补录经期开始日期不能重复")
        if len(deduped) == 1:
            raise PydanticCustomError(
                "period_too_few",
                "补录经期开始日期至少需要 2 个（才能构成至少 1 个完整周期）",
            )

        for prev, cur in zip(deduped, deduped[1:]):
            gap = (cur - prev).days
            if not (_PERIOD_MIN_GAP_DAYS <= gap <= _PERIOD_MAX_GAP_DAYS):
                raise PydanticCustomError(
                    "period_gap_out_of_range",
                    f"相邻经期开始日期间隔需在 "
                    f"{_PERIOD_MIN_GAP_DAYS}~{_PERIOD_MAX_GAP_DAYS} 天之间",
                )
        return deduped


class LoginRequest(UserAuthRequest):
    # Keep legacy accounts usable; new registrations still require 8+ characters.
    password: str = Field(min_length=1, max_length=128)


class RegisterResponse(StatusResponse):
    user_id: int | None = None
    period_dates_recorded: int | None = Field(
        default=None, description="本次注册补录写入的经期开始日期数量"
    )


class LoginResponse(StatusResponse):
    user_id: int | None = None
    username: str | None = None


class SessionResponse(StatusResponse):
    user_id: int | None = None
    username: str | None = None
