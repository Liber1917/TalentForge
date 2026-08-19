from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SalaryRange(BaseModel):
    min_annual: int | None = Field(default=None, ge=0)
    max_annual: int | None = Field(default=None, ge=0)
    currency: str = "CNY"


class NarrativeIdentity(BaseModel):
    """人格叙事轨：自然语言为主，结构化字段待研究扩展。"""

    identity: str = ""
    values: list[str] = Field(default_factory=list)
    deep_drives: list[str] = Field(default_factory=list)
    cognitive_style: str | None = None


class StructuralPosition(BaseModel):
    """结构位置（D12）：研究阶段，自然语言 + 可扩展。"""

    material_conditions: str = ""
    social_relations: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class RevealedChoice(BaseModel):
    """显示性偏好（D6/O2）：投/拒/接offer 行为流。"""

    job_id: str
    choice: str  # applied | rejected | passed | offer_accepted | offer_rejected
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""


class OrdinalPreference(BaseModel):
    """岗位属性偏好序（序数，非基数）。"""

    attribute: str  # salary | tech_stack | work_mode | growth | stability | location | company_type
    ordering: list[str] = Field(default_factory=list)  # 偏好从高到低


class Profile(BaseModel):
    """求职者画像：显式层 + 双轨 + 结构位置。"""

    name: str
    email: str | None = None
    years_experience: float = 0.0
    skills: list[str] = Field(default_factory=list)
    desired_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    salary_expectation: SalaryRange | None = None
    deal_breakers: list[str] = Field(default_factory=list)
    narrative: NarrativeIdentity = Field(default_factory=NarrativeIdentity)
    utility_preferences: dict[str, OrdinalPreference] = Field(default_factory=dict)
    structural_position: StructuralPosition = Field(default_factory=StructuralPosition)
    revealed_preferences: list[RevealedChoice] = Field(default_factory=list)