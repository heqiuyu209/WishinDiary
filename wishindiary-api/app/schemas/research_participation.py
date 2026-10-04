from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool


class ParticipationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participate: StrictBool
    policy_version: str | None = None
    adult_confirmed: StrictBool = False


class ResearchBackground(BaseModel):
    """Optional self report, not a diagnosis or a fixed day adjustment."""
    model_config = ConfigDict(extra="forbid")
    age_band: Literal["under18", "18_24", "25_34", "35_44", "45_plus"] | None = None
    pregnancy: StrictBool | None = None
    breastfeeding: StrictBool | None = None
    hormonal_contraception: StrictBool | None = None
    diagnosed_pcos: StrictBool | None = None
    diagnosed_thyroid: StrictBool | None = None

